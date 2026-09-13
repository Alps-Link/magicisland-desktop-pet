#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从成品 exe（或成品 zip）里取回不进 git 的素材。

仓库里没有、但必须有的素材有三样：
  live2d_viewer/   Live2D 角色模型 —— 游戏内解包素材，没有公开来源，只能从那台已有机器拷
  models/          语音模型（sherpa Paraformer）+ 向量模型（bge），体积超 GitHub 限制
  music_starter/   内置音乐（仅打包版首次运行用）
它们都原样打进了成品 exe。本脚本用 PyInstaller 自带的 CArchiveReader 把它们抽出来，
不需要交互式工具，也不猜归档格式。

用法（在仓库根目录）：

    # 看一眼 exe 里有哪些顶层素材目录
    python tools/extract_assets.py 桌宠合集_压缩包/阿尔卑斯桌宠.zip --list

    # 把 Live2D 模型抽到该宠物目录下
    python tools/extract_assets.py 桌宠合集_压缩包/阿尔卑斯桌宠.zip live2d_viewer --out 桌宠合集/阿尔卑斯桌宠自用

    # 抽完并和手头的原始目录逐文件比对 SHA256
    python tools/extract_assets.py dist/AlpsPet.exe live2d_viewer --out %TEMP%/chk --check 桌宠合集/阿尔卑斯桌宠自用/live2d_viewer

参数说明：
    第一个参数   成品 .exe，或只含一个 exe 的成品 .zip（zip 会先解出 exe 到临时目录，退出时删除）
    其余参数     要抽取的顶层目录名，可给多个（live2d_viewer models music_starter）
    --out        输出目录，默认当前目录；按归档内原始路径落盘并保留子目录
    --list       只列出顶层目录及文件数，不抽取
    --check      抽完后与指定目录逐文件比对 SHA256
"""

import argparse
import hashlib
import os
import shutil
import sys
import tempfile
import zipfile


def resolve_exe(path):
    """把 .exe / .zip 统一成 exe 路径；zip 的情况返回临时目录供清理。"""
    if not os.path.exists(path):
        sys.exit(f'[x] 找不到文件：{path}')
    low = path.lower()
    if low.endswith('.exe'):
        return path, None
    if low.endswith('.zip'):
        with zipfile.ZipFile(path) as z:
            exes = [i for i in z.infolist()
                    if not i.is_dir() and i.filename.lower().endswith('.exe')]
            if len(exes) != 1:
                sys.exit(f'[x] 该 zip 里应恰好有 1 个 exe，实际 {len(exes)} 个：{path}')
            tmp = tempfile.mkdtemp(prefix='pet_extract_')
            target = os.path.join(tmp, os.path.basename(exes[0].filename))
            with z.open(exes[0]) as src, open(target, 'wb') as dst:
                shutil.copyfileobj(src, dst, 1024 * 1024)
        print(f'[i] 已从 zip 解出 exe → {target}（{os.path.getsize(target) / 1048576:.1f} MB）')
        return target, tmp
    sys.exit(f'[x] 只支持成品 .exe 或 .zip：{path}')


def load_reader(exe):
    try:
        from PyInstaller.archive.readers import CArchiveReader
    except ImportError:
        sys.exit('[x] 需要 PyInstaller 才能读 onefile 归档：python -m pip install pyinstaller')
    return CArchiveReader(exe)


def toc_names(reader):
    """归档内条目名统一成反斜杠形式，便于按顶层目录归组。"""
    return {n.replace('/', '\\'): n for n in reader.toc}


def group_by_top(names):
    tops = {}
    for name in names:
        tops.setdefault(name.split('\\', 1)[0], []).append(name)
    return tops


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def main():
    ap = argparse.ArgumentParser(add_help=True, description='从成品 exe/zip 里取回素材')
    ap.add_argument('archive', help='成品 .exe 或成品 .zip')
    ap.add_argument('prefixes', nargs='*', help='要抽取的顶层目录名，如 live2d_viewer')
    ap.add_argument('--out', default='.', help='输出目录，默认当前目录')
    ap.add_argument('--list', action='store_true', help='只列出顶层目录，不抽取')
    ap.add_argument('--check', help='抽完后与该目录逐文件比对 SHA256')
    args = ap.parse_args()

    exe, tmpdir = resolve_exe(args.archive)
    try:
        reader = load_reader(exe)
        names = toc_names(reader)
        tops = group_by_top(names)

        if args.list or not args.prefixes:
            print(f'[i] 归档条目共 {len(names)} 个，顶层目录如下（* 为素材目录）：')
            for top in sorted(tops):
                mark = '*' if top in ('live2d_viewer', 'models', 'music_starter') else ' '
                print(f'  {mark} {top:<28} {len(tops[top]):>5} 个文件')
            if not args.prefixes and not args.list:
                print('\n[i] 未指定要抽取的目录，仅列出。抽取示例：'
                      '\n    python tools/extract_assets.py <exe|zip> live2d_viewer --out <宠物目录>')
            return

        for prefix in args.prefixes:
            want = [n for n in names if n == prefix or n.startswith(prefix + '\\')]
            if not want:
                print(f'[x] 归档里没有 {prefix}/，可用：{", ".join(sorted(tops))}')
                continue
            total = 0
            for name in want:
                out_path = os.path.join(args.out, name)
                os.makedirs(os.path.dirname(out_path), exist_ok=True)
                data = reader.extract(names[name])
                with open(out_path, 'wb') as f:
                    f.write(data)
                total += len(data)
            print(f'[√] {prefix}/ → {os.path.abspath(os.path.join(args.out, prefix))}'
                  f'（{len(want)} 个文件，{total / 1048576:.1f} MB）')

            if args.check:
                src_dir = os.path.join(args.check.rstrip('\\/'), prefix) \
                    if os.path.basename(args.check.rstrip('\\/')) != prefix else args.check
                bad, missing, checked = [], [], 0
                for name in want:
                    rel = name.split('\\', 1)[1] if '\\' in name else os.path.basename(name)
                    a = os.path.join(args.out, name)
                    b = os.path.join(src_dir, rel)
                    if not os.path.exists(b):
                        missing.append(rel)
                        continue
                    checked += 1
                    if sha256_file(a) != sha256_file(b):
                        bad.append(rel)
                print(f'[i] 比对 {src_dir}：核对 {checked}，不符 {len(bad)}，原始目录缺失 {len(missing)}')
                for rel in (bad + missing)[:5]:
                    print(f'    - {rel}')
    finally:
        if tmpdir:
            shutil.rmtree(tmpdir, ignore_errors=True)


if __name__ == '__main__':
    main()
