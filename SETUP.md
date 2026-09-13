# SETUP —— 从零要自己搞的东西（下载 / 克隆 / 拷贝）

> **只是想用桌宠、不想碰源码？** 那不用看这个文件：直接下成品压缩包
> <https://pan.baidu.com/s/1L1Kmug1nU5xrdlyIfI09uA> 提取码 `9xvm`，解压双击 exe 即可（8 只各一个包）。

仓库里**已经有**的东西不用管：代码、`角色设定/`、`tools/`、8 只共用的 `桌宠合集/_pylibs/`。

下面这些是仓库里**没有**、必须自己弄到手的。命令都在**仓库根目录**执行，PowerShell 直接粘贴即可；
统一写 `curl.exe` 而不是 `curl`——PowerShell 里 `curl` 是 `Invoke-WebRequest` 的别名，参数不一样。
（实测：`hf download` CLI 走 hf-mirror 会失败，本机 Python 的 `urllib` 也不会跟随镜像的 308 跳转，**这两个都别用**。）

## 总览

| # | 要搞的东西 | 体积 | 来源 | 缺了会怎样 |
|---|---|---|---|---|
| 0 | Python 3.10.11 x64 + Git | 29MB | python.org / git-scm.com | 跑不起来 |
| 1 | 本仓库 | 30MB | `git clone` | —— |
| 2 | 13 个 Python 包（含 torch） | ~3GB | PyPI，见 `requirements.txt` | 跑不起来 / 缺功能 |
| 3 | 语音模型 sherpa Paraformer | 244MB | hf-mirror + GitHub Release ↓下面有命令 | 语音功能变灰"不可用" |
| 4 | 向量模型 bge-small-zh-v1.5 | 96MB | hf-mirror ↓ | 记忆向量召回退化为旧排序 |
| 5 | Live2D 角色模型 `live2d_viewer/` | 31.4MB（8 只合计） | ⚠️ **无公开来源**：从本机 `LIVE2D/` 随身包拷回，或从成品 zip 抽 | **没有角色画面，等于空壳** |
| 6 | 内置音乐 `music_starter/`（可选） | 17MB | 同上（或自己放任意音频） | 打包版首次运行无内置曲 |

> 第 3～6 项都是**每只桌宠一份**。换机器时只补你打算跑的那只就行；想 8 只全跑见文末"省空间"。

---

## 0. 前置

**Python 3.10.11 x64**（必须 3.10，3.11/3.12 下 `_pylibs` 里的 `_sherpa_onnx.cp310-win_amd64.pyd`
和 `live2d-py` 的 Cubism native 都会 import 失败）

```powershell
curl.exe -L -o "$env:TEMP\python-3.10.11-amd64.exe" "https://www.python.org/ftp/python/3.10.11/python-3.10.11-amd64.exe"
```

双击安装，**勾上 "Add python.exe to PATH"**。装完 `python -V` 应显示 `Python 3.10.11`。
（这个安装包本机实测 29,037,240 字节。）

**Git**：<https://git-scm.com/download/win> 下载安装（或 `winget install --id Git.Git -e`）。

## 1. 克隆仓库

```powershell
git clone https://github.com/Alps-Link/magicisland-desktop-pet.git
cd magicisland-desktop-pet
```

私有仓库，需要你的 GitHub 凭据；如果弹不出登录窗口，先执行一次
`git config --global credential.helper manager`。

## 2. Python 包

```powershell
python -m pip install -r requirements.txt
```

`sherpa-onnx` / `pypinyin` **不要** pip 装：仓库里的 `桌宠合集/_pylibs/` 已自带，主脚本会自动挂 `sys.path`。
`easyocr` / `sentence-transformers` 会连带装上 **torch**（数 GB），是这一步最耗时的部分。
国内可加清华源提速：`python -m pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple`

## 3. 语音模型（sherpa Paraformer + silero VAD）

**推荐直接跑脚本**——一条命令下齐 3 个文件并自动核对 SHA256，只用标准库（pip 装依赖之前也能跑）：

```powershell
python tools\fetch_models.py                  # 默认下到 阿尔卑斯桌宠自用
python tools\fetch_models.py 薇薇 洛洛          # 指定桌宠（短名或目录名都行）
python tools\fetch_models.py --all            # 8 只全下（244MB × 8）
python tools\fetch_models.py --check-only     # 只核对已有文件，不下载
python tools\fetch_models.py --with-bge       # 连 bge 向量模型一起下（打包 exe 才需要）
```

它是幂等的：已下好且校验通过的文件会跳过，中断了重跑即可。

**想手动下**也行，代码只读其中 **3 个文件**（`Alps.py` 里写死的清单），所以下这 3 个就够：

```powershell
$M = "桌宠合集\阿尔卑斯桌宠自用\models\sherpa-onnx-paraformer-zh-2023-09-14"
New-Item -ItemType Directory -Force $M | Out-Null

curl.exe -L -o "$M\model.int8.onnx" "https://hf-mirror.com/csukuangfj/sherpa-onnx-paraformer-zh-2023-09-14/resolve/main/model.int8.onnx"
curl.exe -L -o "$M\tokens.txt" "https://hf-mirror.com/csukuangfj/sherpa-onnx-paraformer-zh-2023-09-14/resolve/main/tokens.txt"
curl.exe -L -o "$M\silero_vad.onnx" "https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/silero_vad.onnx"
```

- 三个文件的官方来源分别是 HF 仓库 `csukuangfj/sherpa-onnx-paraformer-zh-2023-09-14`（apache-2.0）
  和 sherpa-onnx 的 GitHub Release；**两个大文件都实测过：下载结果与本机现有文件 SHA256 逐字节一致**（见第 7 节）。
- 备选：GitHub 上还有整包 `sherpa-onnx-paraformer-zh-2023-09-14.tar.bz2`（234MB，含 test_wavs 等 20 个文件），
  但 `silero_vad.onnx` 仍要单独下，所以除非你要跑官方示例，按上面 3 条更省事。
- **不下会怎样**（实测）：程序照常启动、角色照常显示，只是点菜单里的「语音识别」会弹一句
  「模型未就绪：语音识别模型加载失败，无法开启。」（日志里是 `语音模型加载失败: No graph was found in the protobuf.`）。
- ⚠️ **临时缓存陷阱**（实测踩过）：模型路径含中文时（桌宠目录都是中文），程序启动会把这 3 个文件复制到
  `%TEMP%\alps_stt_paraformer`（C++ 层打不开中文路径），此后**即使 `models\` 目录不存在，语音也能靠这份缓存正常跑**——
  所以"语音能用"不等于"模型下好了"，换机器/清理临时目录后才是真实状态。首次启动因为要复制，会多占一份 244MB 临时空间。

## 4. 向量模型（bge-small-zh-v1.5）

**只跑源码的话这一步可以跳过**：非打包版走的是 HF 名字 `BAAI/bge-small-zh-v1.5`，
配合代码里预设的 `HF_ENDPOINT=https://hf-mirror.com`，首次用到时会自动下载到 HF 缓存。

但**打包 exe 必须有本地一份**（spec 会把该目录打进包），需要下面 9 个文件（`pytorch_model.bin` 是重复权重，不用下）：

```powershell
$B = "桌宠合集\阿尔卑斯桌宠自用\models\bge-small-zh-v1.5"
New-Item -ItemType Directory -Force "$B\1_Pooling" | Out-Null

foreach ($f in "config.json","config_sentence_transformers.json","modules.json","sentence_bert_config.json",
               "special_tokens_map.json","tokenizer.json","tokenizer_config.json","vocab.txt") {
  curl.exe -sL -o "$B\$f" "https://hf-mirror.com/BAAI/bge-small-zh-v1.5/resolve/main/$f"
}
curl.exe -sL -o "$B\1_Pooling\config.json" "https://hf-mirror.com/BAAI/bge-small-zh-v1.5/resolve/main/1_Pooling/config.json"
curl.exe -sL -o "$B\model.safetensors" "https://hf-mirror.com/BAAI/bge-small-zh-v1.5/resolve/main/model.safetensors"
```

## 5. Live2D 角色模型 `live2d_viewer/` —— 唯一没有下载源的东西

每只 24~65 个文件（`live2d_viewer/model/`：`.moc3` + 贴图 + `model3.json` + `motions/`）是**游戏内解包的 Live2D 素材**，
没有公开下载地址，也没法用其他模型直接替代（`model3.json` 里点着 Touch_0/Idling 等具体动作文件）。8 只各自独立，共 345 文件 / 31.4MB。两条路：

**（a）从本仓库的 `LIVE2D/` 随身包拷回**（推荐，最快）

仓库根有一个 `LIVE2D/`（不进 git，所以不会随 clone 下来，但它一直在这台机器/你的备份里），
结构是 `LIVE2D\<短名>\live2d_viewer\…`，8 只各一份：

```powershell
$L = "LIVE2D"; $P = "桌宠合集"
foreach ($n in "阿尔卑斯","希雅拉","薇薇","可可","洛洛","莫娜卡","艾丽卡","卡梅莉亚") {
  robocopy "$L\$n\live2d_viewer" "$P\${n}桌宠自用\live2d_viewer" /E /NFL /NDL /NJH /NJS
}
```

细节（逐只清单、反向同步、新增桌宠怎么加）见 `LIVE2D/README.md`。

**（b）从任意一只成品 zip/exe 里抽**（已实测：抽出来的 48 个文件与原始目录 SHA256 逐字节一致）

```powershell
python tools\extract_assets.py "桌宠合集_压缩包\阿尔卑斯桌宠.zip" live2d_viewer --out "桌宠合集\阿尔卑斯桌宠自用"
```

同一条命令还能把第 3、4、6 项一起捞回来（成品 exe 里就带着它们，实测 models 30 个文件同样逐字节一致）：

```powershell
python tools\extract_assets.py "桌宠合集_压缩包\阿尔卑斯桌宠.zip" models music_starter --out "桌宠合集\阿尔卑斯桌宠自用"
python tools\extract_assets.py "桌宠合集_压缩包\阿尔卑斯桌宠.zip" --list     # 先看包里有哪些顶层目录
```

> 也就是说：**只要手上还剩任意一只成品 zip，第 3~6 项就都不需要联网下载。**

## 6. 内置音乐（可选）

`music_starter/故事的开端.wav`（17,920,048 字节）来源待确认，同样只能从旧机器拷或用第 5 节的 (b) 抽。
它只在**打包版首次运行**、且曲库为空时被放进取库，源码运行完全不读——不放也不影响任何功能，
也可以自己丢一个音频文件进去当内置曲（文件名不限，`_seed_bundled_music` 会把整个目录搬进曲库）。

## 7. 校验（下完对一遍，避免下到半截的文件）

`models/` 下这几个文件的 SHA256 应当与本机现有版本一致：

| 文件 | 字节 | SHA256 |
|---|---|---|
| `sherpa-onnx-paraformer-zh-2023-09-14\model.int8.onnx` | 243,371,218 | `f36a0433bcf096bd6d6f11b80a3ac8bed110bdca632fe0d731df8d1a84475945` |
| `sherpa-onnx-paraformer-zh-2023-09-14\tokens.txt` | 75,756 | `59aba8873a2ed1e122c25fee421e25f283b63290efbde85c1f01a853d83cb6e6` |
| `sherpa-onnx-paraformer-zh-2023-09-14\silero_vad.onnx` | 643,854 | `9e2449e1087496d8d4caba907f23e0bd3f78d91fa552479bb9c23ac09cbb1fd6` |
| `bge-small-zh-v1.5\model.safetensors` | 95,827,648 | `354763b9b1357bc9c44f62c6be2276321081ed2567773608c0d0785b61d5a026` |
| `bge-small-zh-v1.5\config.json` | 776 | `3853a7979202c348751b753e36f579c41d8da7d36af617d3d907e1fc9b441f2a` |
| `bge-small-zh-v1.5\tokenizer.json` | 439,125 | `48cea5d44424912a6fd1ea647bf4fe50b55ab8b1e5879c3275f80e339e8fae26` |
| `bge-small-zh-v1.5\vocab.txt` | 109,540 | `45bbac6b341c319adc98a532532882e91a9cefc0329aa57bac9ae761c27b291c` |

```powershell
$P = "桌宠合集\阿尔卑斯桌宠自用"
Get-FileHash "$P\models\sherpa-onnx-paraformer-zh-2023-09-14\*.onnx","$P\models\sherpa-onnx-paraformer-zh-2023-09-14\tokens.txt",
             "$P\models\bge-small-zh-v1.5\*","$P\models\bge-small-zh-v1.5\1_Pooling\*" -Algorithm SHA256 |
  ForEach-Object { "{0}  {1,12:N0}  {2}" -f $_.Hash, (Get-Item $_.Path).Length, (Split-Path $_.Path -Leaf) }
```

第 5 节 (b) 抽出来的素材，可以用 `--check` 直接和手头原始目录比对：

```powershell
python tools\extract_assets.py "桌宠合集_压缩包\阿尔卑斯桌宠.zip" live2d_viewer --out "$env:TEMP\chk" --check "桌宠合集\阿尔卑斯桌宠自用\live2d_viewer"
```

## 8. 跑起来

```powershell
cd 桌宠合集\阿尔卑斯桌宠自用
python Alps.py            # 或双击 run.bat
```

首次运行自建 `userdata/`（曲库、记忆库、配置都在里面），API key 在程序内的设置界面填
（地址 / 密钥 / 模型，兼容 OpenAI 格式）。

## 9. 实测记录：只补 live2d_viewer 能跑到什么程度

在**干净检出**（226 个追踪文件、无 `models/`、无 `userdata/`、无 `LIVE2D/`）上补了一份 `live2d_viewer` 后实际跑过：

| 观察项 | 结果 |
|---|---|
| 角色渲染 | ✅ 正常。日志 `load modelSetting: …\live2d_viewer\model\alps.model3.json` → `create model: alps.moc3` → 21 个动作全部载入，无 `CRASH`；枚举窗口可见 `ViviLayeredWnd`（400×320，LAYERED，visible）+ 主窗 `阿尔卑斯桌宠` |
| 语音识别 | ⚠️ 若确实没有 `models/` → 启动日志 `语音模型加载失败: No graph was found in the protobuf.`，点「语音识别」弹「模型未就绪…无法开启」；其余功能不受影响 |
| 记忆向量 | ✅ 自动从 `hf-mirror` 取（第二次起走本地 HF 缓存），日志 `记忆向量模型已加载: BAAI/bge-small-zh-v1.5` |
| 对话/记忆/话题/陪看 | ⚠️ 需要先在设置界面填 API key，否则不会回话（启动不报错） |
| 首次启动自建 | `userdata\`（`alps.log`、`memory.db`、`music\`） |

结论：**"补 live2d_viewer → 角色就能正常显示互动"是成立的**（点击、拖拽、眨眼、待机都由渲染层自理，不依赖网络）；
但要"对话类功能可用"还差 API key，要"语音可用"还差那 3 个模型文件。

## 附：8 只共用一份模型（省 ~2.3GB）

`models/`（335MB）和 `live2d_viewer/`（2.6MB）本来是每只一份。只想跑源码、又不想复制 8 遍，
可以让其余 7 只指向第一只的目录（目录联接，程序只读这些文件）：

```powershell
$src = "桌宠合集\阿尔卑斯桌宠自用"
foreach ($pet in "希雅拉","薇薇","可可","洛洛","莫娜卡","艾丽卡","卡梅莉亚") {
  $dst = "桌宠合集\${pet}桌宠自用"
  New-Item -ItemType Junction -Path "$dst\models" -Target "$PWD\$src\models" -ErrorAction SilentlyContinue | Out-Null
  New-Item -ItemType Junction -Path "$dst\live2d_viewer" -Target "$PWD\$src\live2d_viewer" -ErrorAction SilentlyContinue | Out-Null
}
```

（打包 exe 时会跟随联接正常读取；不想用联接就只能老老实实复制。）
