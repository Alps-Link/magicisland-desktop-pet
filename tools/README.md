# 验证台子（tools/）

改渲染器（`live2d_renderer.py` / `vivi_renderer.py` / `erica_renderer.py`）时的离屏验证脚本。
**统一用法：在宠物目录里跑**（脚本自己会 import 该目录的渲染器），路径用 `$PWD`：

```powershell
$env:PYTHONIOENCODING = "utf-8"
Set-Location "<仓库根>\桌宠合集\阿尔卑斯桌宠自用"
python "$env:TEMP\..."   # 台子脚本放在仓库 tools\ 下，按下面各条换路径
```

## 一、接缝 / 点击路径

| 脚本 | 用途 |
|---|---|
| `seam_ab.py <宠物目录> <渲染器> <模块名> <mouse_x> [变体] [touch序号]` | **A/B 台子**：把源码复制成临时副本、只做一处文本变体（单一变量），扫接缝窗口的单帧阶跃。变体：`asis` / `nobreath` / `nodrag` / `seamshort` / `noclick` |
| `seam_table.py <宠物目录> <渲染器> <模块名> <mouse_x>` | 打印接缝前后每帧全部参数 + 循环状态（`active_scene`/`trans_return`/`pending_face_restore`） |
| `trace_at.py <宠物目录> <渲染器> <模块名> <mouse_x> <起> <止> [touch序号]` | **看形状**：打印某时间窗的逐帧值。判"真跳变"还是"动作自带的快速位移"必须看这个 |

## 二、表情 / 回归路径

| 脚本 | 用途 |
|---|---|
| `emotion_scan.py <宠物目录> <渲染器> <模块名> <mouse_x> [表情]` | 切表情 → 2.5s → 回中性，分别量「进入段 / 回归瞬间 / 回归之后」最大单帧阶跃 |
| `mouth_lifecycle.py <宠物目录> <渲染器> <模块名> [表情]` | 复刻 App 真实说话时序：推 `0.3` → 2s 推 `0` → （模拟气泡淡出）回中性 |
| `transition_audit.py <宠物目录> <渲染器> <模块名> [mouse_x]` | **过渡审计**：入场结束 / 点击 / 动画中再点 / 表情快切 / 睡眠 / 醒来 / 陪玩动作，一次跑完 |

## 三、深层诊断

| 脚本 | 用途 |
|---|---|
| `state_probe.py <宠物目录> <渲染器> <模块名> <now|old> [zip] [表情] [mouse_x]` | 循环状态探针：逐帧记录 `active_scene`/`expression_active`/`trans_return`/`trans_to` + 参数。`old` = 直接跑 zip 里打包当时的字节码 |
| `drag_variant.py <宠物目录> <渲染器> <模块名> <asis|alwaysdrag|exprdrag|nodrag|noangle> [mx]` | drag 守卫各变体对比（结论：**换成 `expression_active` 无效**，`noangle` 才有效——见 §4） |

## 四、成品核验（对打包好的 zip）——**已随打包线撤出仓库**

`verify_zips.py`、`exe_report.py`、`check_drag_guard.py`、`make_manifest.py` 这几个只服务"自己出成品"，
已按用户决定撤出 git（文件仍在本地 `tools/`，`.gitignore` 忽略；换机器要单独拷）。用法备忘：

| 脚本 | 用途 |
|---|---|
| `verify_zips.py` | 8 个 zip 的体积 + **从 exe 反查渲染器版本标记**（判据分两族：l2d 看 `expression_active`；薇薇/艾丽卡 看 `mouth_disp` 且无 `restore_resume_idle`） |
| `exe_report.py <zip> <模块名> <当前源码>` | 打包版 vs 当前的**函数级字节码差异**（忽略行号/跳转，注释自动过滤） |
| `check_drag_guard.py <zip> <模块名>` | 反查 `Drag` 调用前的守卫，确认打进去的是哪一版 |
| `make_manifest.py <标签>` | 生成/更新 `BUILD_MANIFEST.md`（zip 体积 + SHA256、8 只源码指纹） |

## 五、最重要的三条经验（省得重踩）

1. **台子必须先等入场演完再点击**（`FirstImpression`）——否则量到的是"入场被强制接管"，结论全错。本仓库台子统一在 `t≥10.5s` 之后才发命令。
2. **单帧阶跃指标会把"快速但连续的斜坡"误判成跳变**——任何超标数都要用 `trace_at.py` 逐帧看形状才能定性（模型自带的甩头每帧 ±2 是正常的）。
3. **改"每帧写某参数"的补丁前先盘"这个参数还有谁在写"**（参数所有权）；回归测试要覆盖**点击/接缝**和**表情/回归待机**两条路径。

## 六、已知无效的修法（别再试）

- ❌ 去掉 drag 守卫 `active_scene is None` → 跳变照旧（+19.52 vs +19.46）
- ❌ 表情期间 drag 全程失效 → 跳变照旧（+19.48），且会让头在表情期完全不跟鼠标
- ✅ 过渡不写 `Angle*`（把回归路径早有的"角度跳过"扩展到表情进入）→ 19.5 → 0.11，代价是表情不再带动头部姿态

## 七、配套工具（不是台子）

| 脚本 | 用途 |
|---|---|
| `check_secrets.py` | pre-commit 钩子：拦截 `userdata/`、API key 等不该入库的内容（`_pylibs/` 已放行） |
| `extract_assets.py <exe\|zip> <目录…> [--out 目标] [--list] [--check 原始目录]` | **从成品 exe/zip 里取回不进 git 的素材**（`live2d_viewer` / `models` / `music_starter`）。换机器时手上只剩成品 zip 也能把素材捞回来（实测 live2d_viewer 48 个、models 30 个文件与原始目录 SHA256 逐字节一致）；用法见 `SETUP.md` §5 |
| `fetch_models.py [桌宠…] [--all] [--with-bge] [--check-only] [--out 目录]` | **一键下载源码运行所需的模型**（语音 3 个文件，自带 SHA256 校验、幂等可重跑）。只用标准库所以 pip 之前也能跑；hf-mirror 的 308 跳转自己补了处理器（`hf download` CLI 走镜像会失败）。用法见 `SETUP.md` §3 |
