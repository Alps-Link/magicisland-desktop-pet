"""循环状态探针：记录 active_scene / expression_active / trans 状态 / 关键参数。
用法：state_probe.py <宠物目录> <渲染器> <模块名> <now|old> [zip] [emo]
"""
import importlib
import io
import marshal
import os
import struct
import sys
import time
import types
import zipfile
import zlib

pet_dir, rfile, modname, mode = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]
zip_path = sys.argv[5] if len(sys.argv) > 5 else 'x'
emo = sys.argv[6] if len(sys.argv) > 6 else 'happy'
mxv = float(sys.argv[7]) if len(sys.argv) > 7 else 1.0
sys.path.insert(0, pet_dir)
os.chdir(pet_dir)
path = os.path.join(pet_dir, rfile)


def old_code(zip_path, modname):
    with zipfile.ZipFile(zip_path) as z:
        n = [x for x in z.namelist() if x.lower().endswith('.exe')][0]
        with z.open(n) as f:
            data = f.read()
    i = data.find(b'PYZ\0')
    start = -1
    while i != -1:
        if data[i + 4:i + 8] == b'\x6f\x0d\x0d\x0a':
            start = i
            break
        i = data.find(b'PYZ\0', i + 1)
    toc = marshal.load(io.BytesIO(data[start + struct.unpack('!I', data[start + 8:start + 12])[0]:]))
    typ, pos, length = [e for e in toc if e[0] == modname][0][1]
    return marshal.loads(zlib.decompress(data[start + pos:start + pos + length]))


src = io.open(path, encoding='utf-8').read().replace('\r\n', '\n')
lines = src.split('\n')
k = [i for i, ln in enumerate(lines) if ln.strip() == 'model.Update()'][-1]
ind = len(lines[k]) - len(lines[k].lstrip())
i4, i8, i12 = ' ' * (ind + 4), ' ' * (ind + 8), ' ' * (ind + 12)
hook = [f"{' ' * ind}# ---- BENCH HOOK ----",
        f"{' ' * ind}if _bench_rec is not None:",
        f"{i4}try:",
        f"{i8}_st = {{}}",
        f"{i8}for _k2, _n2 in (('scene', 'active_scene'), ('expr', 'expression_active'),",
        f"{i12}('ret', 'trans_return'), ('to', 'trans_to'), ('mx', 'mouse_x')):",
        f"{i12}try:",
        f"{i12}    _st[_k2] = eval(_n2)",
        f"{i12}except Exception:",
        f"{i12}    _st[_k2] = None",
        f"{i8}for _p2, _ex in (('AX', \"model.GetParameterValue(list(model.GetParamIds()).index('ParamAngleX'))\"),",
        f"{i12}('MO', \"model.GetParameterValue(list(model.GetParamIds()).index(MOUTH_PARAM))\" if MOUTH_PARAM else '0')):",
        f"{i12}try:",
        f"{i12}    _st[_p2] = eval(_ex)",
        f"{i12}except Exception:",
        f"{i12}    _st[_p2] = None",
        f"{i8}_bench_rec.append((time.time(), _st))",
        f"{i4}except Exception:",
        f"{i8}pass"]
src2 = '\n'.join(lines[:k + 1] + hook + lines[k + 1:])
src2 = src2.replace('import live2d.v3 as live2d', 'import live2d.v3 as live2d\n_bench_rec = None\n', 1)
if mode == 'old':
    io.open(os.path.join(pet_dir, '_bench_sp_src.py'), 'w', encoding='utf-8', newline='').write(src2)
    mod = types.ModuleType('bench_sp')
    mod.__file__ = path
    exec(old_code(zip_path, modname), mod.__dict__)
    # 旧版走 patch 路线
    import live2d.v3 as live2d
    rec = []
    names = []
    state = {'on': False}
    cls = live2d.LAppModel
    orig = cls.Update

    def patched(self, *a, **k):
        r = orig(self, *a, **k)
        if state['on']:
            try:
                if not names:
                    names.extend(self.GetParamIds())
                d = {}
                for key, pname in (('AX', 'ParamAngleX'),):
                    d[key] = self.GetParameterValue(names.index(pname)) if pname in names else None
                for key, pname in (('MO', 'ParamParmOpenY'), ('MO2', 'ParamMouthOpenY')):
                    if pname in names:
                        d[key] = self.GetParameterValue(names.index(pname))
                rec.append((time.time(), d))
            except Exception:
                pass
        return r
    cls.Update = patched
    r = mod.Live2DRenderer(None)
    r.start(width=600, height=480)
    t0 = time.time()
    time.sleep(1.0)
    r.track_mouse(1.0, 0.0)
    while time.time() - t0 < 10.5:
        time.sleep(0.02)
    state['on'] = True
    t_emo = time.time()
    r.set_emotion(emo)
    time.sleep(1.5)
    state['on'] = False
    r.destroy()
    time.sleep(0.4)
    print('### %s 打包版（%s）' % (modname, emo))
    for t, d in rec:
        dt = t - t_emo
        if -0.05 <= dt <= 0.20:
            print('  %+6.3f  AX=%-8s ParmOpenY=%-7s MouthOpenY=%s' % (dt, d.get('AX'), d.get('MO'), d.get('MO2')))
    sys.exit(0)

io.open(os.path.join(pet_dir, '_bench_sp.py'), 'w', encoding='utf-8', newline='').write(src2)
mod = importlib.import_module('_bench_sp')
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
time.sleep(1.5)
r.destroy()
time.sleep(0.4)
print('### %s 现在版（%s）  [scene/expr/ret/to=是否有过渡/mx]' % (modname, emo))
last = None
for t, d in rec:
    dt = t - t_emo
    if -0.05 <= dt <= 1.6 and (dt < 0.25 or abs(dt*10 - round(dt*10)) < 0.03):
        print('  %+6.3f  scene=%-6s expr=%-6s ret=%-5s to=%-5s mx=%s  AX=%s ParmOpenY=%s'
              % (dt, d.get('scene'), d.get('expr'), d.get('ret'),
                 bool(d.get('to')) if d.get('to') is not None else None, d.get('mx'),
                 ('%.2f' % d['AX']) if d.get('AX') is not None else '-',
                 ('%.2f' % d['MO']) if d.get('MO') is not None else '-'))
