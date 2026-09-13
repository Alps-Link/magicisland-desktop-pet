"""提交前密钥/隐私扫描：拦 API key、token、私钥、以及不该进仓库的路径。
用法：
    python tools/check_secrets.py            # 扫暂存区（git diff --cached）
    python tools/check_secrets.py --all      # 扫工作区全部待追踪文件
退出码非 0 = 有命中，提交应中止。
"""
import os
import re
import subprocess
import sys

ROOT = subprocess.run(['git', 'rev-parse', '--show-toplevel'], capture_output=True, text=True).stdout.strip()
if not ROOT:
    print('不在 git 仓库里'); sys.exit(2)

FORBIDDEN_PATH = re.compile(
    r'(^|/)(userdata|models|live2d_viewer|LIVE2D|music_starter|_old_extract|_dist_final|build|dist|__pycache__|\.dsh|\.dsh-meow)(/|$)'
    r'|\.(exe|zip|onnx|safetensors|log|db|mp3|wav|png|jpg|jpeg)$'
    r'|(^|/)(custom_api\.json|llm_config\.json|.*_api_key\.json|token\.json|cookies\.json|\.env)$', re.I)

# 例外：`_pylibs/`（8 只共用的 Python 依赖）已按用户要求入库，
# 里面的 .dll/.pyd 不该被上面的"二进制扩展名"规则拦下。
ALLOW_PATH = re.compile(r'(^|/)_pylibs/', re.I)

# 值型特征：常见密钥格式 / 长随机串 / 私钥头
VALUE_PAT = re.compile(
    r'(sk-[A-Za-z0-9_\-]{12,}'
    r'|(?:api[_-]?key|token|secret|password)\s*[:=]\s*["\']([A-Za-z0-9_\-]{16,})["\']'
    r'|-----BEGIN [A-Z ]*PRIVATE KEY-----)'
    r'|gg-[A-Za-z0-9_\-]{20,}', re.I)

TEXT_EXT = {'.py', '.json', '.txt', '.md', '.bat', '.ps1', '.spec', '.cfg', '.ini', '.yaml', '.yml', '.toml', '.js', '.ts'}


def is_forbidden(rel):
    if ALLOW_PATH.search(rel):
        return False
    return bool(FORBIDDEN_PATH.search(rel))


def staged_files():
    out = subprocess.run(['git', 'ls-files', '-z'], capture_output=True).stdout.decode('utf-8', 'replace')
    return [f for f in out.split('\0') if f]


def scan_all():
    hits = []
    for dp, dn, fn in os.walk(ROOT):
        dn[:] = [d for d in dn if d not in ('.git',)]
        for f in fn:
            p = os.path.join(dp, f)
            rel = os.path.relpath(p, ROOT).replace(os.sep, '/')
            if is_forbidden(rel):
                continue
            if os.path.splitext(f)[1].lower() not in TEXT_EXT:
                continue
            try:
                txt = open(p, encoding='utf-8', errors='ignore').read()
            except OSError:
                continue
            for m in VALUE_PAT.finditer(txt):
                hits.append((rel, m.group(0)[:40]))
    return hits


def main():
    files = staged_files()
    bad_path = [f for f in files if is_forbidden(f)]
    if bad_path:
        print('!! 不该进仓库的路径（%d）：' % len(bad_path))
        for f in bad_path:
            print('   ', f)
    hits = scan_all()
    if hits:
        print('!! 疑似密钥（%d 处，工作区扫描）：' % len(hits))
        for f, v in hits[:20]:
            print('    %-52s %s' % (f, v[:30]))
    if not bad_path and not hits:
        print('扫描通过：无禁用路径、无密钥特征（共 %d 个追踪文件）' % len(files))
        return 0
    print('\n提交已中止。请把上述文件加入 .gitignore 并 git rm --cached。')
    return 1


if __name__ == '__main__':
    sys.exit(main())
