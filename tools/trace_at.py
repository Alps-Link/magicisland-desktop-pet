"""逐帧细看某个时间窗：trace_at.py <宠物目录> <渲染器> <模块名> <mouse_x> <t_start> <t_end> [touch_idx]
时间以"点击时刻"为 0 点。
"""
import glob
import importlib
import io
import json
import os
import sys
import time

pet_dir, rfile, modname, mx = sys.argv[1], sys.argv[2], sys.argv[3], float(sys.argv[4])
t_a, t_b = float(sys.argv[5]), float(sys.argv[6])
tti = int(sys.argv[7]) if len(sys.argv) > 7 else 0
sys.path.insert(0, pet_dir)
os.chdir(pet_dir)

src = io.open(os.path.join(pet_dir, rfile), encoding='utf-8', newline='').read().replace('\r\n', '\n')
lines = src.split('\n')
idxs = [i for i, ln in enumerate(lines) if ln.strip() == "model.Update()"]
k = idxs[-1]
ind = len(lines[k]) - len(lines[k].lstrip())
i4, i8, i12 = " " * (ind + 4), " " * (ind + 8), " " * (ind + 12)
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
src = "\n".join(lines[:k + 1] + hook + lines[k + 1:])
src = src.replace("_ti = random.randint(0, len(touch_durations) - 1)", f"_ti = {tti}")
head = "import live2d.v3 as live2d"
src = src.replace(head, head + "\n_bench_rec = None\n_bench_names = []\n", 1)
tmp = os.path.join(pet_dir, "_bench_tr.py")
io.open(tmp, "w", encoding="utf-8", newline="").write(src)

W = ('ParamAngleX', 'ParamAngleY', 'ParamAngleZ', 'ParamAngleX2', 'ParamAngleY2', 'ParamAngleZ2',
     'ParamBodyAngleX', 'ParamBodyAngleY', 'ParamBodyAngleZ', 'ParamBreath')
try:
    mod = importlib.import_module("_bench_tr")
    rec = []
    mod._bench_rec = rec
    r = mod.Live2DRenderer(None)
    r.start(width=600, height=480)
    t0 = time.time()
    time.sleep(1.0)
    r.track_mouse(mx, 0.0)
    while time.time() - t0 < 10.5:
        time.sleep(0.02)
    r.track_mouse(mx, 0.0)
    click_t = time.time() - t0
    r.begin_click()
    while time.time() - t0 < 20.0:
        time.sleep(0.02)
    r.destroy()
    time.sleep(0.4)
    rows = [(t - t0 - click_t, p) for t, p in rec]
    names = [n for n in W if n in (mod._bench_names or [])]
    print('### %s 点击后 %.2f~%.2fs 逐帧（%d 帧/秒左右）' % (modname, t_a, t_b, len(rows) // 20))
    print('  dt    ' + ''.join('%9s' % n.replace('Param', '') for n in names))
    prev = None
    for t, p in rows:
        if not (t_a <= t <= t_b):
            continue
        line = '%6.3f ' % t + ''.join('%9.2f' % p.get(n, 0) for n in names)
        if prev is not None:
            big = max(names, key=lambda n: abs(p.get(n, 0) - prev.get(n, 0)))
            d = p.get(big, 0) - prev.get(big, 0)
            if abs(d) > 0.05:
                line += '   <<' + big.replace('Param', '') + ' %+.2f' % d
        print(line)
        prev = p
finally:
    try:
        os.remove(tmp)
    except Exception:
        pass
