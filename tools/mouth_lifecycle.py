"""复刻 App 的真实说话生命周期（含气泡淡出时的 restore_expression）：
t=0 气泡显示 → set_emotion(emo) + set_mouth(0.3)
t=2s        → set_mouth(0)                （App 的固定 2 秒）
t=6s        → set_emotion('normal')       （气泡淡出 → restore_expression）
用法：mouth_lifecycle.py <宠物目录> <渲染器> <模块名> [emo]
"""
import importlib
import io
import os
import sys
import time

pet_dir, rfile, modname = sys.argv[1], sys.argv[2], sys.argv[3]
emo = sys.argv[4] if len(sys.argv) > 4 else 'happy'
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
tmp = os.path.join(pet_dir, '_bench_lc.py')
io.open(tmp, 'w', encoding='utf-8', newline='').write(src)
try:
    mod = importlib.import_module('_bench_lc')
    rec = []
    mod._bench_rec = rec
    r = mod.Live2DRenderer(None)
    r.start(width=600, height=480)
    t0 = time.time()
    time.sleep(1.0)
    r.track_mouse(1.0, 0.0)
    while time.time() - t0 < 10.5:
        time.sleep(0.02)
    t_bubble = time.time()
    r.set_emotion(emo)
    r.set_mouth(0.3)          # 气泡显示
    time.sleep(2.0)
    t_push0 = time.time()
    r.set_mouth(0.0)          # App 固定 2 秒
    time.sleep(4.0)
    t_fade = time.time()
    r.set_emotion('normal')   # 气泡淡出 → restore_expression
    time.sleep(3.0)
    r.destroy()
    time.sleep(0.4)
    W = ('ParamParmOpenY', 'ParamMouthOpenY', 'ParamMouthSmall', 'ParamSayNi', 'ParamAngleZ')
    wn = [n for n in W if n in (mod._bench_names or [])]
    print('### %s（emo=%s）气泡 t=0 · App推0 t=+2s · 气泡淡出 t=+6s' % (modname, emo))
    print('   秒      ' + ''.join('%11s' % n.replace('Param', '') for n in wn))
    cur = None
    for t, p in sorted(rec):
        dt = round(t - t_bubble, 1)
        if dt < 0 or dt > 8.0 or dt == cur:
            continue
        cur = dt
        tag = ''
        if abs(dt - 2.0) < 0.06:
            tag = '   << App 推 0'
        if abs(dt - 6.0) < 0.06:
            tag = '   << 气泡淡出→回中性'
        print('  %+5.1f  ' % dt + ''.join('%11.3f' % p.get(n, 0) for n in wn) + tag)
finally:
    try:
        os.remove(tmp)
    except Exception:
        pass
