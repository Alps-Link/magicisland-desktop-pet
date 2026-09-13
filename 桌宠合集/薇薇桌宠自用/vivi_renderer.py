"""
Live2D 离屏渲染 — FBO → 直接 alpha RGBA → layered window
"""
import os, math, time, json, threading, sys, random
import numpy as np
from PIL import Image
import pygame
from pygame.locals import *
from OpenGL.GL import *
import live2d.v3 as live2d

def _get_base_dir():
    try:
        return sys._MEIPASS
    except AttributeError:
        return os.path.dirname(os.path.abspath(__file__))

MODEL_DIR = os.path.join(_get_base_dir(), 'live2d_viewer', 'model')


# 反预乘查表：_UNPREMUL[a] = round(255 * 65536 / a)（定点 16.16），a=0 时为 0。
# 帧数据保持预乘 alpha（Windows 分层窗口本就要求预乘），
# 只有 tk Label 降级路径需要直通 alpha，才用它换算。
_UNPREMUL = np.zeros(256, dtype=np.uint32)
for _i in range(1, 256):
    _UNPREMUL[_i] = round(255 * 65536 / _i)


def _unpremultiply(img):
    """预乘 alpha → 直通 alpha（仅降级用 Label 显示时调用）"""
    arr = np.array(img, copy=True)
    a = arr[..., 3]
    m = a > 0
    if m.any():
        sub = arr[..., :3][m].astype(np.uint32)
        sub *= _UNPREMUL[a[m]][:, None]
        sub >>= 16
        np.minimum(sub, 255, out=sub)
        arr[..., :3][m] = sub.astype(np.uint8)
    return Image.fromarray(arr, 'RGBA')

# 眼睛在模型画布（800×640，中心为原点）里的纵向位置：自画布顶部往下约 20 单位（≈画面高的 13%）。
# 用于把"注视基准行"随渲染构图一起换算 —— 放大（聚焦缩放）时基准线才会跟着脸走。
# 旧实现是按 char_size 的固定 16%（≈画面高 20%，落在脖子/上胸），偏高。
EYE_ROW_IN_CANVAS = 69.7


class Live2DRenderer:
    def __init__(self, tk_root):
        self._thread = None; self._cmd_q = []; self._q_lock = threading.Lock()
        self._ready = False
        self._frame = None; self._frame_lock = threading.Lock()
        self._on_frame = None

    def enqueue(self, cmd):
        """线程安全地追加渲染命令"""
        with self._q_lock:
            self._cmd_q.append(cmd)

    def start(self, width=600, height=480, on_click=None, on_frame=None):
        self._cmd_q = []
        self._on_frame = on_frame
        def run(): _render(self, width, height)
        self._thread = threading.Thread(target=run, daemon=True)
        self._thread.start(); self._ready = True

    def get_frame(self):
        with self._frame_lock:
            if self._frame is None: return None
            return self._frame

    def get_frame_pil(self):
        with self._frame_lock:
            if self._frame is None: return None
            w, h, d = self._frame
        return Image.frombuffer('RGBA', (w, h), d, 'raw', 'RGBA', 0, 1)

    def set_emotion(self, e):
        self.enqueue(('emotion', e))
    def set_expression(self, idx):
        self.enqueue(('expression', idx))
    def start_idle(self):
        self.enqueue(('idle',))
    def set_mouth(self, v):
        self.enqueue(('mouth', v))
    def set_zoom(self, fz):
        """聚焦缩放：渲染端先裁剪再读回，放大时省读回量与反预乘开销"""
        self.enqueue(('zoom', float(fz)))

    def set_size(self, w, h):
        """显示尺寸：渲染区域按它 ×（聚焦缩放）推算，读回裁剪后仍是它 —— 放大也 1:1"""
        self.enqueue(('size', int(w), int(h)))

    def begin_click(self):
        self.enqueue(('click',))
    def track_mouse(self, mx, my):
        self.enqueue(('mouse', mx, my))
    def destroy(self):
        self._ready = False
        self.enqueue(('quit',))
    def is_ready(self): return self._ready


def _render(bridge, width, height):
    os.environ['SDL_VIDEO_WINDOW_POS'] = '-9999,-9999'
    pygame.init()
    pygame.display.set_mode((width, height), DOUBLEBUF | OPENGL | HIDDEN)

    live2d.init(); live2d.glInit()
    model = live2d.LAppModel()
    model.LoadModelJson(os.path.join(MODEL_DIR, 'Vivi.model3.json'))
    model.SetAutoBreathEnable(True); model.SetAutoBlinkEnable(True)

    # 嘴部参数名因模型而异（部分模型导出为 ParamParmOpenY），探测实际存在的名字
    try:
        _param_ids = list(model.GetParamIds())
    except Exception:
        _param_ids = []
    MOUTH_PARAM = next((p for p in ('ParamMouthOpenY', 'ParamParmOpenY') if p in _param_ids), None)

    # 读取所有动作组的时长（用于「播一遍定格」与「循环点前收尾」）
    touch_durations = []      # Touch 组各动作时长
    emo_durations = {}        # (组名, 索引) -> 时长
    try:
        with open(os.path.join(MODEL_DIR, 'Vivi.model3.json'), 'r', encoding='utf-8') as _f:
            _md = json.load(_f)
        for _g, _items in (_md.get('FileReferences', {}).get('Motions', {}) or {}).items():
            for _i, _it in enumerate(_items):
                try:
                    with open(os.path.join(MODEL_DIR, _it['File']), 'r', encoding='utf-8') as _f:
                        _d = json.load(_f).get('Meta', {}).get('Duration', 0) or 0
                except Exception:
                    _d = 0.0
                if _g == 'Touch':
                    touch_durations.append(_d)
                emo_durations[(_g, _i)] = _d
    except Exception:
        pass
    expression_stop = 0.0  # 表情动画播完一圈定格的时间戳

    # 回归系统：motion 停止后参数定格在末帧（实测确认，不会自动回默认），
    # 因此回归采用「StopAllMotions + 0.5s smoothstep 手动插值回进入前快照」。
    param_ids = list(model.GetParamIds())
    defaults = [model.GetParameterValue(i) for i in range(len(param_ids))]
    # 眼球参数由鼠标追踪每帧接管，不参与回归插值（参数分层，避免对抗）
    # 角度参数参与回归，但回归期间冻结 Drag（不传鼠标偏移），避免与回归插值拉锯
    restore_ids = [pid for pid in param_ids if pid not in ('ParamEyeBallX', 'ParamEyeBallY')]
    restore_defaults = [defaults[param_ids.index(pid)] for pid in restore_ids]
    restore_active = False  # 是否正在手动回归
    restore_from = None     # 回归起点参数快照
    restore_start = 0.0
    RESTORE_DUR = 0.7       # 回归时长（秒）
    mouth_level = 0.0   # 嘴部开合目标（App 的 mouth 命令推送）
    mouth_disp = 0.0    # 实际写入值（速率限制 0.25/帧，避免闭嘴时一跳）

    fbo = glGenFramebuffers(1); tex = glGenTextures(1)
    glBindFramebuffer(GL_FRAMEBUFFER, fbo)
    glBindTexture(GL_TEXTURE_2D, tex)
    glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA, width, height, 0, GL_RGBA, GL_UNSIGNED_BYTE, None)
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR)
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)
    glFramebufferTexture2D(GL_FRAMEBUFFER, GL_COLOR_ATTACHMENT0, GL_TEXTURE_2D, tex, 0)
    # Live2D 的遮罩(clipping mask)依赖模板缓冲：离屏 FBO 必须挂 depth-stencil，
    # 否则被遮罩裁掉的部分（描边/阴影网格）会露出来
    rbo = glGenRenderbuffers(1)
    glBindRenderbuffer(GL_RENDERBUFFER, rbo)
    glRenderbufferStorage(GL_RENDERBUFFER, GL_DEPTH24_STENCIL8, width, height)
    glFramebufferRenderbuffer(GL_FRAMEBUFFER, GL_DEPTH_STENCIL_ATTACHMENT, GL_RENDERBUFFER, rbo)
    glBindFramebuffer(GL_FRAMEBUFFER, 0)

    glClearStencil(0)
    glViewport(0, 0, width, height)
    glMatrixMode(GL_PROJECTION); glLoadIdentity(); glOrtho(0, width, height, 0, -1, 1)
    glMatrixMode(GL_MODELVIEW); glLoadIdentity()

    # 模型画布 800×640（5:4），FBO 600×540（10:9）。二者宽高比接近，
    # 不做 letterbox——让 Cubism 自然占满 viewport，统一缩放无变形。
    # 缩放 0.92 让模型占画面 ~90%，留白最小；锚点 0.44 脸在上 1/4 处。
    _s = min(width / 800.0, height / 640.0) * 0.78
    _ay = height * 0.44

    clock = pygame.time.Clock(); cmd_idx = 0; mx, my = 0.0, 0.0
    zoom = 1.0  # 聚焦缩放：渲染区域 = 显示尺寸 × zoom
    disp_w, disp_h = width, height   # 显示尺寸（主线程推送）
    act_w, act_h = width, height     # 活动渲染区域（FBO 分配尺寸为上限）

    def apply_area():
        """按 显示尺寸 × 聚焦缩放 设定渲染区域；上限是 FBO 分配尺寸。
        这样任何缩放档位读回的都是显示尺寸的真实像素（不是把小块放大）。"""
        nonlocal act_w, act_h, _s, _ay
        z = max(1.0, zoom)
        act_w = max(1, min(int(disp_w * z), width))
        act_h = max(1, min(int(disp_h * z), height))
        glViewport(0, 0, act_w, act_h)
        glEnable(GL_SCISSOR_TEST)
        glScissor(0, 0, act_w, act_h)          # 只清活动区域，别白清整个大缓冲
        glMatrixMode(GL_PROJECTION); glLoadIdentity()
        glOrtho(0, act_w, act_h, 0, -1, 1)
        glMatrixMode(GL_MODELVIEW); glLoadIdentity()
        _s = min(act_w / 800.0, act_h / 640.0) * 0.78
        _ay = act_h * 0.44
        # 注视基准行（画面像素，自窗口顶往下）：模型锚点 - 画布半高 + 眼睛在画布里的偏移
        bridge.face_row = int(_ay - _s * 320 + EYE_ROW_IN_CANVAS * _s)

    active_emo = None      # 当前情绪（None/normal = 待机）
    # 说话情绪 → (动作组名, 组内索引)，来自用户的映射文件
    EMOTION_MAP = {
        'relaxed':   ('Expression', 18),  # Face_Talk2
        'surprised': ('Expression', 14),  # Face_Surprise1
        'hurried':   ('Expression', 9),   # Face_Serious1
        'happy':     ('Expression', 12),  # Face_Smile1
        'shy':       ('Expression', 16),  # Face_Surprise3
        'worried':   ('Scene', 7),        # 08.motion
        'sleep':     ('Expression', 6),   # Face_Sad2（休息姿态）
    }
    model.StartMotion('Intro', 0, 3)
    intro_end = time.time() + 7.483  # Vivi_Intro 7.483s：自然播完（Loop=false）后切待机

    try:
        while bridge._ready:
            clock.tick(60)
            in_intro = bool(intro_end and time.time() <= intro_end)
            while cmd_idx < len(bridge._cmd_q):
                c = bridge._cmd_q[cmd_idx]; cmd_idx += 1
                if c[0] == 'quit': bridge._ready = False; break
                elif in_intro and c[0] in ('emotion', 'expression', 'test_motion', 'click'):
                    continue
                elif c[0] == 'emotion':
                    emo = c[1]
                    expression_stop = 0
                    restore_active = False
                    if emo == 'normal':
                        # 回到待机：定格表情 → 手动平滑回归进入前快照 → Idling 接管
                        active_emo = None
                        model.StopAllMotions()
                        restore_from = [model.GetParameterValue(param_ids.index(pid)) for pid in restore_ids]
                        restore_start = time.time()
                        restore_active = True
                    else:
                        # sleep 也是普通表情（映射决定休息姿态，不强制闭眼）
                        active_emo = emo
                        model.StopAllMotions()
                        target = EMOTION_MAP.get(emo)
                        if target:
                            model.StartMotion(target[0], target[1], 3)
                            # 播一遍定格：在循环接点前停掉动画，定格表情末帧
                            _d = emo_durations.get(target, 0) or 0
                            expression_stop = time.time() + max(0.05, _d - 0.1)
                        else:
                            model.StartRandomMotion('Idling', 1)
                elif c[0] == 'expression':
                    expression_stop = 0
                    restore_active = False
                    model.StopAllMotions()
                    model.StartMotion('Expression', c[1], 4)
                elif c[0] == 'idle':
                    expression_stop = 0
                    restore_active = False
                    active_emo = None
                    model.StopAllMotions()
                    model.StartRandomMotion('Idling', 6)
                    mouth_level = 0.0                            # 闭嘴（每帧写入生效）
                    if MOUTH_PARAM:
                        model.SetParameterValue(MOUTH_PARAM, 0.0)
                    model.SetParameterValue('ParamMouthWidth', 0.0)
                elif c[0] == 'test_motion':
                    expression_stop = 0
                    restore_active = False
                    model.StopAllMotions()
                    model.StartMotion(c[1], c[2], 5)
                elif c[0] == 'click':
                    # 触摸：播随机触摸动画（优先级 5 立刻插入），并把 Idling 以更低优先级
                    # 排队 —— Touch 播完后由 Cubism 用动作自身的淡入淡出接管呼吸，
                    # 全程不 StopAllMotions、不写回参数：既无呼吸瞬跳，也不会在鼠标拖到
                    # 极限时因"剥离 drag"算错基准位而前冲
                    active_emo = None
                    expression_stop = 0
                    restore_active = False
                    # 先清掉当前动作（否则新一轮触摸会因优先级不高于它而被拒），再播触摸动作
                    model.StopAllMotions()
                    if touch_durations:
                        _ti = random.randint(0, len(touch_durations) - 1)
                        model.StartMotion('Touch', _ti, 3)
                    else:
                        model.StartRandomMotion('Touch', 3)
                elif c[0] == 'wake':
                    # 苏醒：播随机触摸动画；同时把 Idling 以更低优先级排队，
                    # 动画播完由 Cubism 自己交叉淡入接管（不硬停、不动参数）
                    active_emo = None
                    expression_stop = 0
                    restore_active = False
                    # 先清掉当前动作（否则新一轮触摸会因优先级不高于它而被拒），再播触摸动作
                    model.StopAllMotions()
                    if touch_durations:
                        _ti = random.randint(0, len(touch_durations) - 1)
                        model.StartMotion('Touch', _ti, 3)
                    else:
                        model.StartRandomMotion('Touch', 3)
                elif c[0] == 'mouth':
                    # 表情动画自带嘴部曲线；仅待机（无表情）时直写嘴部，避免加算
                    if MOUTH_PARAM:
                        mouth_level = float(c[1])   # 只记录，由每帧写入
                elif c[0] == 'mouse':
                    mx, my = c[1], c[2]
                elif c[0] == 'zoom':
                    zoom = max(1.0, float(c[1]))
                    apply_area()
                elif c[0] == 'size':
                    disp_w = max(1, min(int(c[1]), width))
                    disp_h = max(1, min(int(c[2]), height))
                    apply_area()
            with bridge._q_lock:
                bridge._cmd_q = bridge._cmd_q[cmd_idx:]
                cmd_idx = 0
            for _ in pygame.event.get(): pass

            if intro_end and time.time() > intro_end:
                intro_end = 0
                model.StartRandomMotion('Idling', 6)

            # 表情动画播完一圈：循环点前定格（末帧姿态保持，无循环跳变）
            if expression_stop and time.time() > expression_stop:
                expression_stop = 0
                model.StopAllMotions()
            # 触摸/唤醒：循环点前停掉，启动手动回归
            # 手动回归：匀速线性插值回中性（模型默认参数），随后 Idling 接管
            # 执行顺序：回归插值在前、鼠标追踪在后（追踪覆盖，避免对抗）
            if restore_active:
                _t = min(1.0, (time.time() - restore_start) / RESTORE_DUR)  # 回归匀速线性
                _goal = restore_defaults  # 回归目标：模型默认中性参数
                for _k, pid in enumerate(restore_ids):
                    if (pid.startswith('ParamAngle') or pid.startswith('ParamBodyAngle')
                        or pid == 'ParamBreath'):  # 呼吸也不写：写一次自动呼吸会在接缝单帧顶 +0.33
                        continue  # 回归不写角度：姿态留在动作末帧，由鼠标 Drag 叠加接管
                    model.SetParameterValue(pid, restore_from[_k] + (_goal[_k] - restore_from[_k]) * _t)
                if _t >= 1.0:
                    restore_active = False
                    model.StartRandomMotion('Idling', 1)  # 回归完成后交回待机动作
            # 动作结束（接缝）：**什么都不做**。
            # 动作按引擎自己的淡入淡出收尾（硬停/排队/交叉淡入都会让自动呼吸单帧顶 +0.33~0.64）；
            # 角度/裙摆残姿由 drag 按绝对位置继续叠加；呼吸交给引擎自动呼吸；嘴由下方"嘴部"一行管。
            # 早期那套"全参数回归 + 重启待机"的收尾已整段删除：它等于又引入一份同样宽的所有权冲突。
            # 嘴的归属：①表情挂着 → 完全交给表情；②表情回归过渡中且没在说话 → 交给过渡（平滑收嘴）；
            #            ③其余情况（含过渡中正在说话）→ 由这里每帧写，收回动作末帧残留 + 跟 App 说话值
            if MOUTH_PARAM and active_emo is None \
                and (not restore_active or mouth_level > 0 or mouth_disp > 0):
                _mt = mouth_level
                mouth_disp += max(-0.25, min(0.25, _mt - mouth_disp))
                model.SetParameterValue(MOUTH_PARAM, mouth_disp)
            model.SetParameterValue('ParamEyeBallX', mx)
            model.SetParameterValue('ParamEyeBallY', my)
            model.Drag(mx * 1.0, my * 0.8)
            model.Update()

            glBindFramebuffer(GL_FRAMEBUFFER, fbo)
            glClearColor(0.0, 0.0, 0.0, 0.0)
            glClear(GL_COLOR_BUFFER_BIT | GL_STENCIL_BUFFER_BIT)   # 模板也要清，遮罩才干净
            glLoadIdentity()
            glTranslatef(act_w / 2, _ay, 0); glScalef(_s, _s, 1)
            model.Draw(); glFlush()

            # 读回：从渲染区域里裁出"显示尺寸"那块（渲染区域=显示尺寸×zoom，故此处恒 1:1）
            fz = max(1.0, zoom)
            crop_w = max(1, int(act_w / fz))
            crop_h = max(1, int(act_h / fz))
            left = (act_w - crop_w) // 2
            # glReadPixels 自下而上：图像顶部对应 GL 的高 y 端
            buf = glReadPixels(left, act_h - crop_h, crop_w, crop_h, GL_RGBA, GL_UNSIGNED_BYTE)
            rgba = np.ascontiguousarray(
                np.frombuffer(buf, np.uint8).reshape(crop_h, crop_w, 4)[::-1])
            _bytes = rgba.tobytes()   # FBO 本身就是预乘 alpha，分层窗口要的正是这个
            with bridge._frame_lock:
                bridge._frame = (crop_w, crop_h, _bytes)
            cb = bridge._on_frame
            if cb is not None:
                try: cb(crop_w, crop_h, _bytes)
                except Exception: pass
            glBindFramebuffer(GL_FRAMEBUFFER, 0)
    except Exception as e:
        import traceback; print(f'[Live2D] {e}'); traceback.print_exc()
    finally:
        glDeleteFramebuffers(1, [fbo]); glDeleteTextures([tex]); glDeleteRenderbuffers(1, [rbo])
        live2d.glRelease(); pygame.quit()
