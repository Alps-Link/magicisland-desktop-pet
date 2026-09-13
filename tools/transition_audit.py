"""动作/表情过渡审计：按 App 真实命令序列跑一遍，逐帧量每个过渡点的单帧阶跃。
覆盖：入场结束 / 连续点击（动画中再点）/ 表情快速切换 / 睡眠→唤醒 / 陪玩动作(action) / 表情中点击
用法：transition_audit.py <宠物目录> <渲染器> <模块名> [mx]
"""
import importlib
import io
import os
import sys
import time

pet_dir, rfile, modname = sys.argv[1], sys.argv[2], sys.argv[3]
mxv = float(sys.argv[4]) if len(sys.argv) > 4 else 1.0
sys.path.insert(0, pet_dir)
os.chdir(pet_dir)
src = io.open(os.path.join(pet_dir, rfile), encoding='utf-8', newline='').read().replace('\r\n', '\n')
L = src.split('\n')
k = [i for i, ln in enumerate(L) if ln.strip() == 'model.Update()'][-1]
ind = len(L[k]) - len(L[k].lstrip())
i4, i8, i12 = ' ' * (ind + 4), ' ' * (ind + 8), ' ' * (ind + 12)
hook = [f"{' ' * ind}# ---- BENCH HOOK ----",
        f"{' ' * ind}if _bench_rec is not None:",
        f"{i4}try:",
        f"{i8}if not _bench_names:",
        f"{i12}_bench_names.extend(model.GetParamIds())",
        f"{i8}_r = {{}}",
        f"{i8}for _i2, _p2 in enumerate(_bench_names):",
        f"{i12}_r[_p2] = model.GetParameterValue(_i2)",
        f"{i8}_bench_rec.append((time.time(), _r))",
        f"{i4}except Exception:",
        f"{i8}pass"]
src = '\n'.join(L[:k + 1] + hook + L[k + 1:])
src = src.replace('import live2d.v3 as live2d', 'import live2d.v3 as live2d\n_bench_rec = None\n_bench_names = []\n', 1)
tmp = os.path.join(pet_dir, '_bench_ta.py')
io.open(tmp, 'w', encoding='utf-8', newline='').write(src)

W = ('ParamAngleX', 'ParamAngleY', 'ParamAngleZ', 'ParamAngleX2', 'ParamAngleY2', 'ParamAngleZ2',
     'ParamBodyAngleX', 'ParamBodyAngleY', 'ParamBodyAngleZ', 'ParamBreath', 'ParamParmOpenY',
     'ParamMouthOpenY', 'ParamMouthSmall', 'ParamSayNi', 'ParamEyeLOpen', 'ParamEyeROpen')

# (标签, 相对开始秒, 命令)
PLAN = [('入场结束', None, None),
        ('点击#1', 4.5, ('click', None)),
        ('动画中再点#2', 5.6, ('click', None)),
        ('表情 happy', 8.5, ('emotion', 'happy')),
        ('0.4s 后切 worried', 9.3, ('emotion', 'worried')),
        ('0.3s 后再切 shy', 9.7, ('emotion', 'shy')),
        ('睡眠', 12.0, ('emotion', 'sleep')),
        ('醒: normal', 14.5, ('emotion', 'normal')),
        ('醒: wake', 14.6, ('wake', None)),
        ('陪玩动作 Action1', 17.5, ('test_motion', ('Action', 1))),
        ('结束前', 20.5, None)]
try:
    mod = importlib.import_module('_bench_ta')
    rec = []
    mod._bench_rec = rec
    r = mod.Live2DRenderer(None)
    t0 = time.time()
    r.start(width=600, height=480)
    time.sleep(0.8)
    r.track_mouse(mxv, 0.0)
    marks = []
    for label, at, cmd in PLAN:
        if at is None:
            continue
        while time.time() - t0 < at:
            time.sleep(0.01)
        r.track_mouse(mxv, 0.0)
        marks.append((label, time.time()))
        if cmd is None:
            continue
        if cmd[0] == 'click':
            r.begin_click()
        elif cmd[0] == 'emotion':
            r.set_emotion(cmd[1])
        elif cmd[0] == 'wake':
            r.enqueue(('wake',))
        elif cmd[0] == 'test_motion':
            r.enqueue(('test_motion', cmd[1][0], cmd[1][1]))
    time.sleep(2.0)
    r.destroy()
    time.sleep(0.4)

    rows = rec
    wn = [n for n in W if n in (mod._bench_names or [])]
    print('### %s  mx=%.1f  帧=%d' % (modname, mxv, len(rows)))
    # 入场结束：以 first_impression_end 为准（各只时长不同，取 3.8s 附近扫描）
    windows = [('入场结束(~3.8s)', t0 + 3.817)]
    windows += [(lab, mt) for lab, mt in marks]
    for lab, mt in windows:
        best = []
        for i in range(1, len(rows) - 1):
            dt = rows[i][0] - mt
            if not (-0.35 <= dt <= 0.45):
                continue
            for n in wn:
                ref = (rows[i - 1][1][n] + rows[i + 1][1][n]) / 2.0
                best.append((abs(rows[i][1][n] - ref), n, rows[i][1][n] - ref, dt))
        best.sort(reverse=True)
        top = best[:3]
        print('  %-20s 最大阶跃 %.3f | %s' % (lab, top[0][0] if top else 0,
              '; '.join('%s=%+.2f@%+.2f' % (n.replace('Param', ''), d, dt) for _, n, d, dt in top)))
finally:
    try:
        os.remove(tmp)
    except Exception:
        pass
