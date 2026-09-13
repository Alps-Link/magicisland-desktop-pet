"""表情回归待机路径的接缝扫描：set_emotion(emotion) → 2.5s → set_emotion('normal')
用法：emotion_scan.py <宠物目录> <渲染器文件> <模块名> <mx> [emotion]
报告：以 set_emotion('normal') 时刻为 0 点，扫全参数单帧阶跃（平滑斜坡会被指标误报，看时间点判断）
"""
import importlib
import io
import os
import sys
import time

pet_dir, rfile, modname, mx = sys.argv[1], sys.argv[2], sys.argv[3], float(sys.argv[4])
emo = sys.argv[5] if len(sys.argv) > 5 else 'happy'
sys.path.insert(0, pet_dir)
os.chdir(pet_dir)

src = io.open(os.path.join(pet_dir, rfile), encoding='utf-8', newline='').read().replace('\r\n', '\n')
lines = src.split('\n')
idxs = [i for i, ln in enumerate(lines) if ln.strip() == 'model.Update()']
k = idxs[-1]
ind = len(lines[k]) - len(lines[k].lstrip())
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
src = '\n'.join(lines[:k + 1] + hook + lines[k + 1:])
head = 'import live2d.v3 as live2d'
src = src.replace(head, head + '\n_bench_rec = None\n_bench_names = []\n', 1)
tmp = os.path.join(pet_dir, '_bench_emo.py')
io.open(tmp, 'w', encoding='utf-8', newline='').write(src)

W = ('ParamAngleX', 'ParamAngleY', 'ParamAngleZ', 'ParamAngleX2', 'ParamAngleY2', 'ParamAngleZ2',
     'ParamBodyAngleX', 'ParamBodyAngleY', 'ParamBodyAngleZ', 'ParamBreath', 'ParamMouthOpenY',
     'ParamParmOpenY', 'ParamSayNi', 'ParamMouthSmall')
try:
    mod = importlib.import_module('_bench_emo')
    rec = []
    mod._bench_rec = rec
    r = mod.Live2DRenderer(None)
    r.start(width=600, height=480)
    t0 = time.time()
    time.sleep(1.0)
    r.track_mouse(mx, 0.0)
    while time.time() - t0 < 10.5:
        time.sleep(0.02)
    r.set_emotion(emo)
    time.sleep(2.5)
    t_ret = time.time()
    r.set_emotion('normal')          # ← 回归待机（Vivi/艾丽卡 在这里 StopAllMotions）
    time.sleep(3.5)
    r.destroy()
    time.sleep(0.4)

    rows = [(t - t_ret, p) for t, p in rec]
    names = [n for n in W if n in (mod._bench_names or [])]
    print('### %s：%s → 2.5s → normal（0 点=收到 normal）' % (modname, emo))
    for lo, hi, tag in ((-2.6, -0.2, '进入表情段'), (-0.2, 0.6, '回归瞬间'), (0.6, 3.4, '回归之后')):
        out = []
        for i in range(1, len(rows) - 1):
            t = rows[i][0]
            if not (lo <= t <= hi):
                continue
            for nm in names:
                v = rows[i][1][nm]
                ref = (rows[i - 1][1][nm] + rows[i + 1][1][nm]) / 2.0
                out.append((abs(v - ref), nm, v - ref, t))
        out.sort(reverse=True)
        top = out[:3]
        worst = top[0][0] if top else 0.0
        print('  %-8s 最大阶跃 %.3f  | %s' % (tag, worst,
              '; '.join('%s=%+.3f@%+.2f' % (n.replace('Param', ''), d, t) for _, n, d, t in top)))
finally:
    try:
        os.remove(tmp)
    except Exception:
        pass
