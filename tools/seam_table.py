"""接缝全参数表：同时记录循环状态变量（pending_face_restore / active_scene / trans_return）。
用法：seam_table.py <宠物目录> <渲染器文件名> <模块名> <mouse_x> [mouse_y]
"""
import glob
import importlib
import io
import json
import os
import sys
import time

pet_dir, rfile, modname, mx = sys.argv[1], sys.argv[2], sys.argv[3], float(sys.argv[4])
my = float(sys.argv[5]) if len(sys.argv) > 5 else 0.0
sys.path.insert(0, pet_dir)
os.chdir(pet_dir)

touch_dur = 3.0
try:
    m3 = glob.glob(os.path.join(pet_dir, "live2d_viewer", "model", "*.model3.json"))[0]
    md = json.load(io.open(m3, encoding="utf-8"))
    touch = md["FileReferences"]["Motions"]["Touch"]
    mp = os.path.join(os.path.dirname(m3), touch[0]["File"])
    touch_dur = float(json.load(io.open(mp, encoding="utf-8"))["Meta"].get("Duration") or 3.0)
except Exception:
    pass

src_path = os.path.join(pet_dir, rfile)
raw = io.open(src_path, encoding="utf-8", newline="").read()
src = raw.replace("\r\n", "\n")
lines = src.split("\n")
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
        f"{i8}for _k2, _n2 in (('__pfr', 'pending_face_restore'), ('__scene', 'active_scene'),",
        f"{i12}('__ret', 'trans_return'), ('__to', 'trans_to'), ('__mx', 'mouse_x'),",
        f"{i12}('__t0', 'trans_start'), ('__td', 'trans_dur_neutral')):",
        f"{i12}try:",
        f"{i12}    _r[_k2] = eval(_n2)",
        f"{i12}except Exception:",
        f"{i12}    _r[_k2] = 0",
        f"{i8}for _i2, _p2 in enumerate(_bench_names):",
        f"{i12}_r[_p2] = model.GetParameterValue(_i2)",
        f"{i8}_bench_rec.append((time.time(), _r))",
        f"{i4}except Exception:",
        f"{i8}pass"]
src = "\n".join(lines[:k + 1] + hook + lines[k + 1:])
src = src.replace("_ti = random.randint(0, len(touch_durations) - 1)", "_ti = 0")
head = "import live2d.v3 as live2d"
src = src.replace(head, head + "\n_bench_rec = None\n_bench_names = []\n", 1)
tmp = os.path.join(pet_dir, "_bench_tab.py")
io.open(tmp, "w", encoding="utf-8", newline="").write(src)

WATCH = ('ParamAngleX', 'ParamAngleZ', 'ParamAngleX2', 'ParamAngleY2', 'ParamBodyAngleX',
         'ParamBodyAngleZ', 'ParamBreath', 'ParamEyeBallX', 'ParamMouthOpenY')

try:
    mod = importlib.import_module("_bench_tab")
    rec = []
    mod._bench_rec = rec
    r = mod.Live2DRenderer(None)
    r.start(width=600, height=480)
    t0 = time.time()
    time.sleep(1.0)
    r.track_mouse(mx, my)
    # FirstImpression = 8.483s，必须等入场演完再点，否则量到的是入场强制接管
    while time.time() - t0 < 10.5:
        time.sleep(0.02)
    r.track_mouse(mx, my)
    click_t = time.time() - t0
    r.begin_click()
    while time.time() - t0 < 20.0:
        time.sleep(0.02)
    r.destroy()
    time.sleep(0.4)

    rows = [(t - t0, p) for t, p in rec]
    names = list(mod._bench_names)
    seam = click_t + touch_dur
    print(f"### {modname} mouse=({mx},{my}) click@{click_t:.2f} 动作结束@{seam:.2f} 帧={len(rows)}")
    hdr = "  t     " + "".join(f"{n.replace('Param','')[:7]:>9}" for n in WATCH)
    print(hdr + "   scene  ret  to  pfr     trans龄")
    prev = None
    post = 0
    for t, p in rows:
        if not (seam - 0.4 <= t <= seam + 6.0):
            continue
        if t > seam + 0.6:
            post += 1
            if post % 5:
                continue
        line = f"{t:6.2f} " + "".join(f"{p.get(n, 0):>9.3f}" for n in WATCH)
        a = p['__t0']
        age = (t - a) if a else 0.0
        line += f"  {str(p['__scene'])[:5]:>5} {str(p['__ret'])[:3]:>4} {1 if p['__to'] else 0:>3} {float(p['__pfr']):>5.0f}  {age:6.2f}"
        if prev is not None:
            big = max(WATCH, key=lambda n: abs(p.get(n, 0) - prev.get(n, 0)))
            d = p.get(big, 0) - prev.get(big, 0)
            if abs(d) > 0.5:
                line += f"   << {big.replace('Param','')} {d:+.2f}"
        print(line)
        prev = p
finally:
    try:
        os.remove(tmp)
    except Exception:
        pass
