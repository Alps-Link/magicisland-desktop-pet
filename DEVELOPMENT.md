# 开发与维护

给"改代码、打包、维护这个仓库"的场景。**使用者请看 [`README.md`](README.md)**，从零搭环境看 [`SETUP.md`](SETUP.md)。

## 铁律：阿尔卑斯先行

**阿尔卑斯（`桌宠合集/阿尔卑斯桌宠自用/`）是模板基准**：共享代码（主脚本、渲染器、`memory_db.py`、
`layered_window.py`）的改动一律**先在它上面做、验证通过**，再同步其余 7 只；
同步只动共享代码区，**绝不触碰宠物专属白名单**（文件头、logger 名、`DEFAULT_PET_NAME`/`PERSONA`、
`LOCAL_TOPICS`、`TOPIC_PROMPT`、问候语、`root.title`、唤醒兜底名、卡梅莉亚装扮功能等）。
每轮改动后 8 只都要编译通过，UI / 渲染改动还要**逐只真跑一次**（编译+标记核对证明不了跑得起来）。
**打包必须等明确指令**，不能顺手打。

## 仓库里有什么

| 进 git | 不进 git（见 `.gitignore`） |
|---|---|
| `桌宠合集/*/`：主脚本、渲染器、`memory_db.py`、`layered_window.py`、图标、`run.bat` | `models/`（sherpa 语音模型 232MB + bge 向量模型 91MB，每只一份） |
| `桌宠合集/_pylibs/`（8 只共用的 Python 依赖：sherpa-onnx、pypinyin，约 26MB） | `live2d_viewer/`（Live2D 角色模型）、`LIVE2D/`（8 只模型的随身拷贝）、`music_starter/`（内置音乐） |
| `角色设定/`（人设档案）、`表情映射.txt`、`_t_topics.py` | `userdata/`（**含 API key、聊天记录、记忆库**）、`custom_api.json` |
| `tools/`：11 个渲染验证台子 + `check_secrets.py` + `extract_assets.py` + `fetch_models.py` | **打包线**：`*Pet.spec`、`tools/make_manifest.py`、`verify_zips.py`、`exe_report.py`、`check_drag_guard.py`、`BUILD_MANIFEST.md`（只服务"自己出成品"，文件仍在硬盘上） |
| `README.md`、`SETUP.md`、`DEVELOPMENT.md`、`CHANGELOG.md`、`requirements.txt`、`LICENSE` | `build/`、`dist/`、`__pycache__/`、`_old_extract/`、成品 `桌宠合集_压缩包/*.zip` |

> **打包线为什么撤出 git**：clone 下来只想跑源码的人用不到它；`*Pet.spec` 里还含本机绝对路径
> （会暴露 Windows 用户名）。文件都还在本地，打包流程完全照旧；**换机器时记得单独拷这批**
> （8 个 spec + 4 个核验工具 + `BUILD_MANIFEST.md`），否则新机器上没法直接出成品。
> 已删除的过时文件：每只目录里的 `pack.bat`（不走 spec，会打出坏 exe）与 `install.bat`（内容还是
> `pip install requests pillow`，早已被 `requirements.txt` 取代）。

> **安全约定**：`userdata/` 与一切 API key 文件永不入库；`tools/check_secrets.py` 已挂 pre-commit 钩子
> （`git config core.hooksPath .githooks`），提交前自动拦截。要放行新一类二进制文件时，得同时改
> `.gitignore` **和** 这个脚本的 `FORBIDDEN_PATH`/`ALLOW_PATH`，否则会被自己的钩子拦住。

## 许可

自己的代码与文档按 **MIT** 发布（见 `LICENSE`）；**注意 MIT 只覆盖作者自己写的部分**：
`live2d_viewer/`、`LIVE2D/`（游戏内解包素材）、`music_starter/`、`models/` 都不在内，
`_pylibs/` 是第三方库（sherpa-onnx Apache-2.0、pypinyin MIT，许可原文随包保留）。

## 关于模型与素材（版权）

| 资产 | 来源 | 入库 |
|---|---|---|
| Live2D 角色模型（`live2d_viewer/` 与 `LIVE2D/`：`.moc3` + 贴图 + 动作） | **游戏内解包素材** | ❌ 不入库（两处都已忽略）；**也不要**放进公开 Release / 对外分发的包里 |
| 内置音乐（`music_starter/故事的开端.wav`） | 来源待确认 | ❌ 不入库，同上 |
| 语音 / 向量模型（`models/`：sherpa `apache-2.0`、bge `BAAI`） | 官方发布，许可允许再分发 | ❌ 仅因体积（单文件 232MB 超 GitHub 100MB 硬限制） |
| Python 依赖（`_pylibs/`） | 第三方库 | ✅ 已入库，便于一处管理 |
| 代码、`角色设定/` 人设档案、`tools/` | 本仓库作者 | ✅ 入库，MIT |

> 含解包素材的成品 exe/zip **仅供自用 / 私下分享**；要公开发布，得先把 `live2d_viewer/` 换成自制或有授权的模型。
> 仓库保持 **Private** 正是出于这一点；若将来转 public，还要先做三件事：把 README/SETUP/DEVELOPMENT 里的
> **网盘链接删掉**（那是分发入口）、确认 `live2d_viewer/` 已换成授权模型、并保留 `LICENSE`。

## 从源码运行

完整步骤（含所有要自己下载的东西、SHA256 校验、从成品 zip 取回素材）见 [`SETUP.md`](SETUP.md)。速览：

1. Windows x64 + **Python 3.10**（`_pylibs` 与 `live2d-py` 都是 cp310 扩展）；
2. `python -m pip install -r requirements.txt`（`sherpa-onnx` / `pypinyin` 不用装，仓库 `_pylibs/` 自带且会自动挂 `sys.path`）；
3. 把 `live2d_viewer/` 放回宠物目录（从 `LIVE2D/` 随身包拷，或用 `tools/extract_assets.py` 从成品 zip 抽）；
   语音模型跑 `python tools/fetch_models.py` 一条命令下齐（3 个文件 243MB，带 SHA256 校验；不下只是"语音识别"用不了）；
4. `cd 桌宠合集/阿尔卑斯桌宠自用 && python Alps.py`。

## 打包发布 exe

> ⚠️ **打包线不在仓库里**（见上面「仓库里有什么」）：`*Pet.spec`、`tools/make_manifest.py`、`verify_zips.py`、
> `exe_report.py`、`check_drag_guard.py`、`BUILD_MANIFEST.md` 都在本地硬盘上、被 `.gitignore` 忽略。
> **换机器 clone 后要出成品，先把这批文件拷过去**——否则 `PyInstaller` 无配方可跑。

见 `.dsh/skills/pack-and-gather`。要点：在宠物目录内跑
`python -m PyInstaller --noconfirm --clean --distpath dist --workpath build {X}Pet.spec`，
**8 只必须串行**（同目录并发必失败），单只约 4.5~6 分钟；成功后 exe 移到 `桌宠合集/_dist_final/`，
压成 `桌宠合集_压缩包/{中文名}桌宠.zip`（deflate level 1，zipfile.testzip 通过才删暂存 exe）。
发布后跑 `python tools/make_manifest.py <标签>` 更新清单，然后 commit + tag + push。

**发布渠道**：成品压缩包上传到**百度网盘** <https://pan.baidu.com/s/1L1Kmug1nU5xrdlyIfI09uA>（提取码 `9xvm`）。
网盘链接是公开可分发的，而包里含 `live2d_viewer/` 解包素材——只私下分享给熟人，别公开传播。
每轮重新打包后记得同步更新网盘里的文件，并在 `BUILD_MANIFEST.md` 里核对体积与 SHA256。

内容核验：打包完可以从 zip 内的 exe 反查渲染器字节码，确认打进去的是当轮最新代码
（`tools/verify_zips.py`；判据分两族——6 只 l2d 看 `expression_active`，薇薇/艾丽卡看 `mouth_disp`）。

## 改渲染器时

渲染器那些"1 帧级"的接缝问题，靠 `tools/` 里 11 个离屏验证台子定位（接缝 A/B、逐帧形状、表情/过渡扫描、
打包字节码反查），用法见 [`tools/README.md`](tools/README.md)。调试必须守住三条纪律：

1. **等入场动画（`FirstImpression`，8.5s）演完再点击**，否则量到的是"入场被强制接管"；
2. **单帧阶跃指标会把"快速但连续的斜坡"误判成跳变**，任何超标数都要逐帧看形状才能定性；
3. **改"每帧写某参数"的补丁前，先盘清这个参数还有谁在写**（参数所有权）；回归要同时覆盖
   "点击 / 接缝"和"表情 / 回归待机"两条路径。

## 版本与成品怎么对应

- 每个发行版打一个标签（如 `v2026.09.13`），标签指向当轮的源码提交；
- `BUILD_MANIFEST.md`（**本地文件，不入库**）记录该轮 8 个成品 zip 的**体积 + SHA256**，以及 8 只主脚本/渲染器的源码指纹；
- 想知道"手上这个 exe 是哪版代码"：用 SHA256 对上清单里的行 → 那个标签就是它；
- 看两版之间改了什么：`git diff v2026.09.12 v2026.09.13`。
