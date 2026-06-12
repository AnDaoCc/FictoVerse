# 小说世界模拟器

本地运行的小说世界模拟器 — 核心状态系统 + AI 聊天 / 角色扮演 / 群聊。

## 功能范围（当前版本）

- **World / Character / State / Event / Save**：世界核心数据管理
- **通用聊天 & 世界聊天**：AI 对话，世界内自动读取规则、角色、状态、事件
- **角色扮演（RP）**：单角色会话、角色卡 PNG/JSON、头像、沉浸模式、会话背景
- **群聊**：跨世界多角色接话（流式 SSE）、成员增删、@指定发言、静音
- **Lorebook / Prompt 分层 / 记忆 / 消息操作**：regen、edit、swipe、/remember
- **多媒体**：会话背景图、浏览器 TTS 朗读（实验性）
- **扩展脚本**：`data/extensions/*.py` Hook 总线（prompt / message / display）
- **世界包**：`.nworld.zip` 本地导入导出，预留云端同步接口
- **多模型支持**：OpenAI、Claude、Gemini、OpenAI 兼容中转站 / Ollama
- **流式输出**：聊天、RP、群聊均支持 SSE 流式
- **静默启动**：双击启动器，无黑窗口，浏览器自动打开

## 一键启动（推荐）

### GUI 启动器（Windows，SillyTavern 风格）

双击 [`GUI启动器.bat`](GUI启动器.bat)（**日常开发推荐**），桌面快捷方式（见下方 **更换启动器图标**），或正式版 **`release/小说世界书启动器/小说世界书启动器.exe`**（见下方 **开发 vs 正式版**）

- 浅色侧栏 + 卡片布局：快捷目录、系统信息、**一键启动**（自动建 `.venv` 并 `pip install` 项目依赖）
- 侧栏：**世界管理 / 环境安装 / 控制台 / 停止服务**
- **世界管理**（无需先启动 Web 服务）：左栏世界书架 + 右栏六个 Tab（世界、角色、状态、文档、Lore、存档），与浏览器内世界详情页能力对齐；支持新建/导入 `.nworld.zip`、角色卡导入导出、头像裁剪上传等。编辑后一键启动即可在 Web 中游玩；服务已运行时修改会自动刷新聊天上下文缓存
- **首次使用**：打开启动器 → 侧栏 **「环境安装」** → **「一键安装最新环境」**（带进度条与步骤提示；自动创建 `.venv`、升级 pip、安装最新依赖并校验）
- **一键启动**成功后默认自动打开浏览器（可在「设置」关闭）；服务运行中主按钮会变为 **「重新打开浏览器」**，误关浏览器可一键重开
- **一键启动**失败时，首页状态栏会显示红色错误摘要，并自动打开控制台日志；服务启动日志见项目 `logs/server-startup.log`
- 若未安装 Python：在环境安装页点击 **「安装 Python（需确认）」**，确认后通过 winget 安装；也可自行从 [python.org](https://www.python.org/downloads/) 安装并勾选 Add to PATH
- 需 Windows 10/11 且已安装 Edge WebView2 运行时（仅 GUI 启动器界面需要）

### 开发 vs 正式版

| 场景 | 入口 | 说明 |
|------|------|------|
| 日常改功能 | [`GUI启动器.bat`](GUI启动器.bat) | 直接读 `src/`，改完重启即生效 |
| 发正式版 | `.\scripts\build_release.ps1` | 自动备份 → 打包 → 输出到 `release/小说世界书启动器/` |
| 历史快照 | `packaging/backup/launcher-dev-*` | 每次发版前自动备份，可对照或回滚 |

改 **Web 主程序**（聊天、世界、设置等）一般只需 `pip install -e .`，**不必**重打 exe；只有改 **启动器壳子**（`src/novel_world/launcher/`）才需要重新发版。

**一键发版**（小启动器 exe，主程序仍用项目 `.venv`）：

```powershell
.\scripts\build_release.ps1
```

双击 `release\小说世界书启动器\小说世界书启动器.exe` 即可（需与 `pyproject.toml` 同目录）。

**带图标的桌面快捷方式**（指向 `GUI启动器.bat`）：

```powershell
.\scripts\create_launcher_shortcut.ps1
```

默认在桌面创建 `小说世界书.lnk`；可传 `-ShortcutName "自定义名称"`。

### 更换启动器图标

图标源文件为 [`packaging/assets/launcher-icon.png`](packaging/assets/launcher-icon.png)。后续换图只需：

1. 覆盖上述 PNG（建议透明底、正方形）
2. 运行 `.\scripts\sync_launcher_icon.ps1`（生成 `launcher-icon.ico`）
3. 若使用 exe：再运行 `.\scripts\build_release.ps1`（或 `.\scripts\build_launcher.ps1`）
4. 若使用桌面快捷方式：再运行 `.\scripts\create_launcher_shortcut.ps1`

开发态 GUI（`GUI启动器.bat` / `pythonw -m novel_world.launcher`）会自动读取项目根下的 `packaging/assets/launcher-icon.ico` 作为窗口图标。

### 制作者信息（Web UI）

浏览器内 **设置** 与 **使用指南** 页底部固定显示开发者信息（界面内无关闭开关）。文案源文件：[`src/novel_world/web/credits.py`](src/novel_world/web/credits.py)。

## 手动启动

```bash
pip install -e ".[dev]"
python -m novel_world.web.run
```

## 使用流程

1. 打开 **设置**，添加模型提供商（API Key / Base URL / 模型名）
2. 进入 **聊天** 或 **群聊**，新建对话并发送消息
3. 在 **世界** 中创建世界观，进入 **世界聊天** 或从角色卡进入 **角色扮演**
4. （可选）在世界详情页 **导出世界包**，或从世界列表 **导入世界包**

### 中转站 / Ollama 配置示例

- 类型选：**OpenAI 兼容（中转站 / Ollama）**
- Base URL：`https://你的中转站/v1` 或 `http://127.0.0.1:11434/v1`
- API Key：中转站提供的 Key（Ollama 可随便填）
- 模型：例如 `gpt-4o-mini` 或 `qwen2.5`

## 数据存储

```
data/
├── app.db              # 模型配置 + 聊天记录
├── server.json         # 当前服务端口信息
├── extensions/         # 用户扩展脚本
├── uploads/            # 头像、背景等上传文件
├── packs/              # 本地同步占位目录
├── active/             # 每个世界一个数据库
│   └── world_<ID>.db
└── saves/              # JSON 存档
```

## 运行测试

```bash
pytest
```

## 命令行（仍可用）

```bash
python -m novel_world create-world "修仙世界"
python -m novel_world list-worlds
```
