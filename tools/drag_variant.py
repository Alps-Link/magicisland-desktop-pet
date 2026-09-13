"""drag 守卫变体探针：asis（现状）/ nodrag（完全不调 Drag）/ alwaysdrag（去掉 active_scene 守卫）
用法：drag_variant.py <宠物目录> <渲染器> <模块名> <variant> [mx] [emo]
"""
import importlib
import io
import os
import sys
import time

pet_dir, rfile, modname, variant = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]
mxv = float(sys.argv[5]) if len(sys.argv) > 5 else 1.0
emo = sys.argv[6] if len(sys.argv) > 6 else 'happy'
sys.path.insert(0, pet_dir)
os.chdir(pet_dir)
src = io.open(os.path.join(pet_dir, rfile), encoding='utf-8', newline='').read().replace('\r\n', '\n')
L = src.split('\n')
di = [i for i, l in enumerate(L) if 'model.Drag(' in l and not l.strip().startswith('#')]
assert len(di) == 1, 'Drag 调用 %d 处' % len(di)
d = di[0]
guard = d - 1
if variant == 'nodrag':
    L[d] = ' ' * (len(L[d]) - len(L[d].lstrip())) + 'pass  # A/B: 不调 Drag'
elif variant == 'exprdrag':
    assert L[guard].strip() == 'if active_scene is None:', L[guard]
    L[guard] = ' ' * (len(L[guard]) - len(L[guard].lstrip())) + 'if expression_active is None:  # A/B: 表情期间 drag 全程失效'
elif variant == 'alwaysdrag':
    assert L[guard].strip() == 'if active_scene is None:', L[guard]
    L[guard] = ' ' * (len(L[guard]) - len(L[guard].lstrip())) + 'if True:  # A/B: 去掉 active_scene 守卫'
src = '\n'.join(L)
if variant == 'noangle':
    OLD = "if trans_return and (pid.startswith('ParamAngle')"
    assert src.count(OLD) == 1, src.count(OLD)
    src = src.replace(OLD, "if (pid.startswith('ParamAngle')  # A/B: 过渡不写角度")
k = [i for i, ln in enumerate(src.split('\n')) if ln.strip() == 'model.Update()'][-1]
LL = src.split('\n')
ind = len(LL[k]) - len(LL[k].lstrip())
i4, i8, i12 = ' ' * (ind + 4), ' ' * (ind + 8), ' ' * (ind + 12)
hook = [f"{' ' * ind}# ---- BENCH HOOK ----",
        f"{' ' * ind}if _bench_rec is not None:",
        f"{i4}try:",
        f"{i8}_st = {{}}",
        f"{i8}_id = list(model.GetParamIds())",
        f"{i8}for _p2 in ('ParamAngleX', 'ParamAngleZ', 'ParamBodyAngleX'):",
        f"{i12}_st[_p2] = model.GetParameterValue(_id.index(_p2)) if _p2 in _id else None",
        f"{i8}try:",
        f"{i12}_st['scene'] = active_scene",
        f"{i8}except Exception:",
        f"{i12}_st['scene'] = None",
        f"{i8}_bench_rec.append((time.time(), _st))",
        f"{i4}except Exception:",
        f"{i8}pass"]
src2 = '\n'.join(LL[:k + 1] + hook + LL[k + 1:])
src2 = src2.replace('import live2d.v3 as live2d', 'import live2d.v3 as live2d\n_bench_rec = None\n', 1)
io.open(os.path.join(pet_dir, '_bench_dv.py'), 'w', encoding='utf-8', newline='').write(src2)
try:
    mod = importlib.import_module('_bench_dv')
    rec = []
    mod._bench_rec = rec
    r = mod.Live2DRenderer(None)
    r.start(width=600, height=480)
    t0 = time.time()
    time.sleep(1.0)
    r.track_mouse(mxv, 0.0)
    while time.time() - t0 < 10.5:
        time.sleep(0.02)
    t_emo = time.time()
    r.set_emotion(emo)
    time.sleep(1.6)
    r.destroy()
    time.sleep(0.4)
    rows = [(t - t_emo, p) for t, p in rec]
    pre = [p for dt, p in rows if -0.08 <= dt <= 0][-1]
    post = [p for dt, p in rows if 0.0 < dt <= 0.05][0]
    late = [p for dt, p in rows if 1.0 <= dt <= 1.2][-1]
    print('%-11s mx=%.1f  AngleX  切前 %.2f → 切入 %.2f   |  1.1s 后 %.2f   | 跳幅 %+.2f'
          % (variant, mxv, pre['ParamAngleX'], post['ParamAngleX'], late['ParamAngleX'],
             post['ParamAngleX'] - pre['ParamAngleX']))
finally:
    for f in ('_bench_dv.py',):
        try:
            os.remove(os.path.join(pet_dir, f))
        except Exception:
            pass
