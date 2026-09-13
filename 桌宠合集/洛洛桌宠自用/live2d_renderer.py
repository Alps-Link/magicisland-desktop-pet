"""
Live2D 离屏渲染
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
EYE_ROW_IN_CANVAS = 20.5


class Live2DRenderer:
    def __init__(self, tk_root):
        self._thread = None
        self._cmd_q = []
        self._q_lock = threading.Lock()
        self._ready = False
        self._frame = None
        self._frame_lock = threading.Lock()
        self._on_frame = None

    def enqueue(self, cmd):
        """线程安全地追加渲染命令"""
        with self._q_lock:
            self._cmd_q.append(cmd)

    def start(self, width=600, height=480, on_click=None, on_frame=None):
        self._cmd_q = []
        self._on_frame = on_frame
        def run(): _render_offscreen(self, width, height)
        self._thread = threading.Thread(target=run, daemon=True)
        self._thread.start()
        self._ready = True

    def get_frame(self):
        with self._frame_lock:
            if self._frame is None: return None
            w, h, data = self._frame
        return Image.frombuffer('RGBA', (w, h), data, 'raw', 'RGBA', 0, 1)

    def set_emotion(self, emotion):
        self.enqueue(('emotion', emotion))

    def set_mouth(self, val):
        self.enqueue(('mouth', val))

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

    def is_ready(self):
        return self._ready


def _render_offscreen(bridge, width, height):
    os.environ['SDL_VIDEO_WINDOW_POS'] = '-9999,-9999'
    pygame.init()
    screen = pygame.display.set_mode((width, height), DOUBLEBUF | OPENGL | HIDDEN)

    live2d.init()
    live2d.glInit()
    model = live2d.LAppModel()
    model.LoadModelJson(os.path.join(MODEL_DIR, 'Roro.model3.json'))

    model.SetAutoBreathEnable(True)
    model.SetAutoBlinkEnable(True)

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
    clock = pygame.time.Clock()
    cmd_idx = 0; mouse_x, mouse_y = 0.0, 0.0
    zoom = 1.0  # 聚焦缩放：渲染区域 = 显示尺寸 × zoom，读回裁剪出显示尺寸那块
    disp_w, disp_h = width, height   # 显示尺寸（主线程推送）
    act_w, act_h = width, height     # 活动渲染区域（FBO 分配尺寸为上限）

    def apply_area():
        """按 显示尺寸 × 聚焦缩放 设定渲染区域；上限是 FBO 分配尺寸。
        这样任何缩放档位读回的都是显示尺寸的真实像素（不是把小块放大）。"""
        nonlocal act_w, act_h
        z = max(1.0, zoom)
        act_w = max(1, min(int(disp_w * z), width))
        act_h = max(1, min(int(disp_h * z), height))
        glViewport(0, 0, act_w, act_h)
        glEnable(GL_SCISSOR_TEST)
        glScissor(0, 0, act_w, act_h)          # 只清活动区域，别白清整个大缓冲
        glMatrixMode(GL_PROJECTION); glLoadIdentity()
        glOrtho(0, act_w, act_h, 0, -1, 1)
        glMatrixMode(GL_MODELVIEW); glLoadIdentity()
        # 注视基准行（画面像素，自窗口顶往下）：画布顶部 + 眼睛在画布里的偏移
        _sc = min(act_w / 800.0, act_h / 640.0) * 0.78
        bridge.face_row = int(act_h * 0.5 - _sc * 320 + EYE_ROW_IN_CANVAS * _sc)
    active_scene = None
    expression_active = None   # 表情（场景）是否还挂着：挂着期间嘴归表情所有，App 说话值不得覆盖
    # 平滑过渡（进入与退出）
    trans_start = 0; trans_dur = 0.5  # 进入表情过渡
    trans_dur_return = 0.7  # 回归常态的过渡时长
    trans_from = {}; trans_to = {}
    trans_return = False      # 是否处于回归中性的过渡中
    # 预加载Scene参数（从 model3.json 读取，兼容命名文件）
    scene_params = {}
    m3_path = os.path.join(MODEL_DIR, 'Roro.model3.json')
    with open(m3_path, 'r', encoding='utf-8') as _f:
        _md = json.load(_f)
    scene_files = _md['FileReferences']['Motions']['Scene']
    for i, sc in enumerate(scene_files):
        fpath = os.path.join(MODEL_DIR, sc['File'])
        try:
            with open(fpath,'r') as f:
                md = json.load(f)
            scene_params[i] = {c['Id']: c['Segments'][1] for c in md['Curves']}
        except: pass
    # Touch 组各动作时长（点击/唤醒随机播放后，循环点前收尾）
    touch_durations = []
    try:
        for _it in (_md.get('FileReferences', {}).get('Motions', {}).get('Touch', []) or []):
            with open(os.path.join(MODEL_DIR, _it['File']), 'r', encoding='utf-8') as _f:
                touch_durations.append(json.load(_f).get('Meta', {}).get('Duration', 0) or 0)
    except Exception:
        pass
    # 模型默认参数即中性：所有动作/表情结束后的统一回归目标
    defaults = {pid: model.GetParameterValue(i) for i, pid in enumerate(model.GetParamIds())}
    # 嘴部参数探测（这两只原本没有该变量：它们忽略 App 的 mouth 命令，
    # 但每帧写回初始值仍需知道参数名）
    try:
        _param_ids = list(model.GetParamIds())
    except Exception:
        _param_ids = []
    MOUTH_PARAM = next((p for p in ('ParamMouthOpenY', 'ParamParmOpenY') if p in _param_ids), None)
    mouth_level = 0.0   # 嘴部开合目标（App 的 mouth 命令推送）
    mouth_disp = 0.0    # 实际写入值（速率限制 0.25/帧，避免闭嘴时一跳）
    model.StartMotion('FirstImpression', 0, 3)
    first_impression_end = time.time() + 2.983  # FirstImpression 2.983s：自然播完（Loop=false）后切待机

    try:
        while bridge._ready:
            dt = clock.tick(60) / 1000.0

            while cmd_idx < len(bridge._cmd_q):
                cmd = bridge._cmd_q[cmd_idx]; cmd_idx += 1
                if cmd[0] == 'quit': bridge._ready = False; break
                elif cmd[0] == 'emotion':
                    # 洛洛表情映射（26 scene，索引从 0 开始）
                    scene_map = {
                        'happy': 24,      # 25.motion3
                        'shy': 15,        # 16.motion3
                        'surprised': 19,  # 20.motion3
                        'worried': 0,     # 01.motion3
                        'hurried': 21,    # 22.motion3
                        'sleep': 4,       # 05.motion3
                    }
                    if cmd[1] in scene_map:
                        target = scene_map[cmd[1]]
                        if target in scene_params:
                            trans_from = {pid: model.GetParameterValue(i)
                                for i, pid in enumerate(model.GetParamIds())}
                            trans_to = scene_params[target]
                            trans_start = time.time()
                            active_scene = target
                            expression_active = target
                            trans_return = False
                    else:
                        # 表情结束：从当前值平滑回归中性（模型默认参数）
                        trans_from = {pid: model.GetParameterValue(i)
                            for i, pid in enumerate(model.GetParamIds())}
                        trans_to = dict(defaults)
                        trans_start = time.time()
                        trans_return = True
                        active_scene = None
                        expression_active = None
                        model.ResetExpressions()
                        model.StartRandomMotion('Idling', 1)
                elif cmd[0] == 'test_motion':
                    model.StartMotion(cmd[1], cmd[2], 5)
                elif cmd[0] == 'click':
                    # 触摸：播随机触摸动画（优先级 5 立刻插入），并把 Idling 以更低优先级
                    # 排队 —— Touch 播完后由 Cubism 用动作自身的淡入淡出接管呼吸，
                    # 全程不 StopAllMotions、不写回参数：既无呼吸瞬跳，也不会在鼠标拖到
                    # 极限时因"剥离 drag"算错基准位而前冲
                    active_scene = None
                    expression_active = None   # 触摸/唤醒接管面部，表情不再拥有嘴
                    trans_to = {}
                    trans_return = False
                    # 先清掉当前动作（否则新一轮触摸会因优先级不高于它而被拒），再播触摸动作
                    model.StopAllMotions()
                    if touch_durations:
                        _ti = random.randint(0, len(touch_durations) - 1)
                        model.StartMotion('Touch', _ti, 3)
                    else:
                        model.StartRandomMotion('Touch', 3)
                elif cmd[0] == 'wake':
                    # 苏醒：播随机触摸动画；同时把 Idling 以更低优先级排队，
                    # 动画播完由 Cubism 自己交叉淡入接管（不硬停、不动参数）
                    active_scene = None
                    expression_active = None   # 触摸/唤醒接管面部，表情不再拥有嘴
                    trans_to = {}
                    trans_return = False
                    # 先清掉当前动作（否则新一轮触摸会因优先级不高于它而被拒），再播触摸动作
                    model.StopAllMotions()
                    if touch_durations:
                        _ti = random.randint(0, len(touch_durations) - 1)
                        model.StartMotion('Touch', _ti, 3)
                    else:
                        model.StartRandomMotion('Touch', 3)
                elif cmd[0] == 'mouth':
                    pass  # 嘴部由表情 scene 控制
                elif cmd[0] == 'mouse':
                    mouse_x, mouse_y = cmd[1], cmd[2]
                elif cmd[0] == 'zoom':
                    zoom = max(1.0, float(cmd[1]))
                    apply_area()
                elif cmd[0] == 'size':
                    disp_w = max(1, min(int(cmd[1]), width))
                    disp_h = max(1, min(int(cmd[2]), height))
                    apply_area()
            with bridge._q_lock:
                bridge._cmd_q = bridge._cmd_q[cmd_idx:]
                cmd_idx = 0

            for event in pygame.event.get(): pass

            if first_impression_end and time.time() > first_impression_end:
                first_impression_end = 0
                model.StopAllMotions()  # 停掉循环的入场动作，Idling 接管
                model.StartRandomMotion('Idling', 4)

            # 触摸/唤醒：动画自然播完（Loop=false）后启动回归（目标=模型默认中性）
            if trans_to and (active_scene is not None or trans_return):
                _tdur = trans_dur_return if trans_return else trans_dur
                t = min(1.0, (time.time() - trans_start) / _tdur)
                if not trans_return:
                    t = t * t * (3.0 - 2.0 * t)  # 表情进入 smoothstep；回归匀速线性
                for pid, target_val in trans_to.items():
                    if pid in ('ParamEyeBallX', 'ParamEyeBallY'):
                        continue  # 眼球由鼠标追踪接管，不参与回归
                    if trans_return and (pid.startswith('ParamAngle') or pid.startswith('ParamBodyAngle')
                                         or pid == 'ParamBreath'):  # 呼吸也不写：写一次自动呼吸会在接缝单帧顶 +0.33
                        continue  # 回归不写角度：姿态留在动作末帧，由鼠标 Drag 叠加接管
                    cur = trans_from.get(pid, target_val)
                    model.SetParameterValue(pid, cur + (target_val - cur) * t)
                if t >= 1.0:
                    if trans_return:
                        # 回归完成：按需重启 Idling
                        trans_return = False
                    active_scene = None
                    trans_to = {}
            # 嘴的归属：①表情挂着 → 完全交给表情；②表情回归过渡中且没在说话 → 交给过渡（平滑收嘴）；
            #            ③其余情况（含过渡中正在说话）→ 由这里每帧写，收回动作末帧残留 + 跟 App 说话值
            if MOUTH_PARAM and active_scene is None and expression_active is None \
                and (not trans_return or mouth_level > 0 or mouth_disp > 0):
                _mt = mouth_level
                mouth_disp += max(-0.25, min(0.25, _mt - mouth_disp))
                model.SetParameterValue(MOUTH_PARAM, mouth_disp)

            model.SetParameterValue('ParamEyeBallX', mouse_x)
            model.SetParameterValue('ParamEyeBallY', mouse_y)
            if active_scene is None:
                model.Drag(mouse_x * 1.0, mouse_y * 0.8)
            model.Update()

            glBindFramebuffer(GL_FRAMEBUFFER, fbo)
            glClearColor(0.0, 0.0, 0.0, 0.0)
            glClear(GL_COLOR_BUFFER_BIT | GL_STENCIL_BUFFER_BIT)   # 模板也要清，遮罩才干净
            glLoadIdentity()
            s = min(act_w/800, act_h/640) * 0.78
            glTranslatef(act_w/2, act_h*0.50, 0); glScalef(s, s, 1)
            model.Draw()
            glFlush()

            # 读回：从渲染区域里裁出"显示尺寸"那块（渲染区域=显示尺寸×zoom，故此处恒 1:1）
            fz = max(1.0, zoom)
            crop_w = max(1, int(act_w / fz))
            crop_h = max(1, int(act_h / fz))
            left = (act_w - crop_w) // 2
            # glReadPixels 自下而上：图像顶部对应 GL 的高 y 端
            buf = glReadPixels(left, act_h - crop_h, crop_w, crop_h, GL_RGBA, GL_UNSIGNED_BYTE)
            arr = np.ascontiguousarray(
                np.frombuffer(buf, dtype=np.uint8).reshape(crop_h, crop_w, 4)[::-1])
            rgba = arr.tobytes()   # FBO 本身就是预乘 alpha，分层窗口要的正是这个
            with bridge._frame_lock:
                bridge._frame = (crop_w, crop_h, rgba)
            cb = bridge._on_frame
            if cb is not None:
                try: cb(crop_w, crop_h, rgba)
                except Exception: pass
            glBindFramebuffer(GL_FRAMEBUFFER, 0)

    except Exception as e:
        import traceback
        print(f'[Live2D] CRASH: {e}')
        traceback.print_exc()
    finally:
        glDeleteFramebuffers(1, [fbo]); glDeleteTextures([tex]); glDeleteRenderbuffers(1, [rbo])
        live2d.glRelease(); pygame.quit()
