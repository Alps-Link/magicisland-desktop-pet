"""接缝 A/B：在临时副本上做文本变体，测同一场景下的接缝跳变。
用法：seam_ab.py <宠物目录> <渲染器文件名> <模块名> <mouse_x> <变体> [touch_idx]
变体：asis / noclick / nobreath / nodrag / seamshort
"""
import glob
import importlib
import io
import json
import os
import sys
import time

pet_dir, rfile, modname, mx, variant = sys.argv[1], sys.argv[2], sys.argv[3], float(sys.argv[4]), sys.argv[5]
tti = int(sys.argv[6]) if len(sys.argv) > 6 else 0
sys.path.insert(0, pet_dir)
os.chdir(pet_dir)

touch_dur = 3.0
try:
    m3 = glob.glob(os.path.join(pet_dir, "live2d_viewer", "model", "*.model3.json"))[0]
    md = json.load(io.open(m3, encoding="utf-8"))
    touch = md["FileReferences"]["Motions"]["Touch"]
    mp = os.path.join(os.path.dirname(m3), touch[tti]["File"])
    touch_dur = float(json.load(io.open(mp, encoding="utf-8"))["Meta"].get("Duration") or 3.0)
except Exception:
    pass

src_path = os.path.join(pet_dir, rfile)
raw = io.open(src_path, encoding="utf-8", newline="").read()
src = raw.replace("\r\n", "\n")

SKIP = "if trans_return and (pid.startswith('ParamAngle') or pid.startswith('ParamBodyAngle')):"
if variant == "nobreath":                      # 收尾过渡不再写 ParamBreath
    assert src.count(SKIP) == 1, src.count(SKIP)
    src = src.replace(SKIP, SKIP.replace("'ParamBodyAngle')):", "'ParamBodyAngle') or pid == 'ParamBreath'):"))
if variant == "nodrag":                        # 收尾后完全不叠加 drag
    DRAG = "model.Drag(mouse_x * 1.2, mouse_y * 1.0)"
    assert src.count(DRAG) == 1, src.count(DRAG)
    src = src.replace(DRAG, "pass")
if variant == "seamshort":                     # 接缝提前 0.2s
    OLD = "max(0.05, touch_durations[_ti])"
    assert src.count(OLD) >= 1, src.count(OLD)
    src = src.replace(OLD, "max(0.05, touch_durations[_ti] - 0.2)")

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
        f"{i8}for _i2, _p2 in enumerate(_bench_names):",
        f"{i12}_r[_p2] = model.GetParameterValue(_i2)",
        f"{i8}_bench_rec.append((time.time(), _r))",
        f"{i4}except Exception:",
        f"{i8}pass"]
src = "\n".join(lines[:k + 1] + hook + lines[k + 1:])
src = src.replace("_ti = random.randint(0, len(touch_durations) - 1)", f"_ti = {tti}")
head = "import live2d.v3 as live2d"
src = src.replace(head, head + "\n_bench_rec = None\n_bench_names = []\n", 1)
tmp = os.path.join(pet_dir, "_bench_ab.py")
io.open(tmp, "w", encoding="utf-8", newline="").write(src)

WATCH = ('ParamAngleX', 'ParamAngleY', 'ParamAngleZ', 'ParamAngleX2', 'ParamAngleY2',
         'ParamAngleZ2', 'ParamBodyAngleX', 'ParamBodyAngleY', 'ParamBodyAngleZ', 'ParamBreath')

try:
    mod = importlib.import_module("_bench_ab")
    rec = []
    mod._bench_rec = rec
    r = mod.Live2DRenderer(None)
    r.start(width=600, height=480)
    t0 = time.time()
    time.sleep(1.0)
    r.track_mouse(mx, 0.0)
    while time.time() - t0 < 10.5:          # 等 FirstImpression（8.483s）演完再点
        time.sleep(0.02)
    r.track_mouse(mx, 0.0)
    click_t = time.time() - t0
    if variant == "noclick":
        while time.time() - t0 < 20.0:
            time.sleep(0.02)
    else:
        r.begin_click()
        while time.time() - t0 < 20.0:
            time.sleep(0.02)
    r.destroy()
    time.sleep(0.4)

    rows = [(t - t0, p) for t, p in rec]
    names = [n for n in WATCH if n in (mod._bench_names or [])]
    if not rows:
        print(f"RESULT|{modname}|{variant}|FAIL|0 帧（渲染循环可能已崩）")
        raise SystemExit(0)
    if variant == "noclick":
        print(f"BASELINE|{modname}|mx={mx}|frames={len(rows)}")
        for want in (10.0, 13.0, 16.0, 19.0):
            best = min(rows, key=lambda r: abs(r[0] - want))
            print(f"   t={best[0]:5.2f} " + " ".join(f"{n.replace('Param','')}={best[1][n]:+.2f}" for n in names))
        raise SystemExit(0)

    seam = click_t + touch_dur
    end = click_t + touch_dur - 0.2
    out = []
    for i in range(1, len(rows) - 1):
        t = rows[i][0]
        if not (end - 0.6 <= t <= seam + 3.0):
            continue
        for nm in names:
            v = rows[i][1][nm]
            ref = (rows[i - 1][1][nm] + rows[i + 1][1][nm]) / 2.0
            out.append((abs(v - ref), nm, v - ref, t))
    out.sort(reverse=True)
    top = out[:4]
    worst = top[0][0] if top else 0.0
    print(f"RESULT|{modname}|{variant}|touch{tti}|mx={mx}|click@{click_t:.2f}|seam@{seam:.2f}|frames={len(rows)}|"
          f"max_step={worst:.3f}|" + "; ".join(f"{n.replace('Param','')}={d:+.3f}@{t:.2f}" for _, n, d, t in top))
finally:
    try:
        os.remove(tmp)
    except Exception:
        pass
