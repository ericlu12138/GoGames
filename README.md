<div align="center">

# GoDojo · 围棋道场

**本地运行的围棋 AI 陪练 —— 自研界面 + KataGo 引擎，免联网、免注册、装完即用**

[![Release](https://img.shields.io/badge/release-v2.1.0-blue)](https://github.com/ericlu12138/GoGames/releases/latest)
[![Platform](https://img.shields.io/badge/platform-Windows%2010%2F11-lightgrey)](https://github.com/ericlu12138/GoGames/releases/latest)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)

[下载安装包](https://github.com/ericlu12138/GoGames/releases/latest) · [使用说明](docs/GoDojo%20使用说明.md) · [交接文档](docs/交接文档.md) · [训练方案](docs/训练方案.md)

</div>

---

## 这是什么

GoDojo 是一个 Windows 桌面围棋程序，用来和 AI 对弈、复盘、练棋。**棋力来自开源的 KataGo 引擎，界面与对局逻辑全部自研**，程序完全在本机运行，不联网、不需要注册账号。

它有两个版本并存，共享同一套核心逻辑：

| | 原版（legacy） | **桌面版 v2.0+（推荐）** |
|---|---|---|
| 代码 | [`legacy/GoDojo.py`](legacy/GoDojo.py) | [`webapp/`](webapp/) |
| 界面 | Python tkinter 原生控件 | HTML/CSS + Canvas 自绘棋盘 |
| 启动 | 需装 Python，双击 `启动围棋.bat` | **双击 `GoDojo.exe`**，不需要 Python |
| 高分屏 | 控件坐标模糊 | 按设备像素比渲染，清晰 |
| 窗口 | 会闪一个黑色控制台 | 无控制台、无地址栏，像独立应用 |
| 多开 | 互相抢 GPU 导致极慢 | 自动拦截第二个实例 |
| 引擎路径 | 硬编码在代码里 | 外置于 `config.json`，可改、可自动探测 |

原版 `GoDojo.py` 完整保留、未被改动 —— 它是这套程序最早的样子，桌面版的规则与引擎封装就是从它搬过来的。

---

## 功能

**对局**

- 棋盘 9 / 13 / 19 路，可执黑或执白
- 让子 0 / 2 / 3 / 4 / 5 子（让子局自动设贴目 0.5 且白方先行）
- AI 强度滑块：每次落子的访问次数，20 – 2000 可调
- 悔棋、提示、停一手、认输、保存棋谱（SGF）

**分析**

- **实时胜率条**：用目差换算，而不是引擎的胜率头（KataGo 在小棋盘上未校准）
- **候选点列表**：前 5 个候选点 + 各自目差 + 访问次数 + 主变（PV）
- **逐手讲评**：每手走完自动评价，掉胜率多会标出来并给出推荐点
- 棋盘上标注最后一手、最近 12 手手数、悬停预览子、A/B/C 推荐点

**三种对手模式**

| 模式 | 说明 |
|---|---|
| 内置 KataGo | 本机引擎直接应手，正常下棋用这个 |
| 外接 AI（文件） | 程序把局面写进 `position.txt`，等外部 AI 把坐标写进 `ai_move.txt` |
| AI 对 AI（双文件） | 黑白分别读 `black_move.txt` / `white_move.txt`，可挂两个不同 AI 互下 |

外接协议见 [`docs/外接AI/协议_给外接AI.md`](docs/外接AI/协议_给外接AI.md) —— 借这个接口可以拿任何模型（包括大语言模型）来下棋。

**快捷键**：`Z`/`U` 悔棋 · `H` 提示 · `P` 停一手 · `A` 分析 · `N` 新局

---

## 下载安装

到 [Releases](https://github.com/ericlu12138/GoGames/releases/latest) 下载 `GoDojo_v2.1.0_Setup.exe`（约 219 MB），双击安装。

**装完直接能玩** —— 不需要装 Python、不需要另配引擎、不需要下载权重，安装包已内置：

| 内容 | 大小 |
|---|---|
| 应用程序 + 运行库 + 前端 | 19 MB |
| KataGo GPU 引擎（OpenCL） | 14.6 MB |
| KataGo CPU 引擎（Eigen，备用） | 14.2 MB |
| 神经网络权重（两引擎共用） | 201.8 MB |
| GPU 调优缓存 | 1.5 KB |

安装时会自动做一次 **引擎预热**（勾选项默认开着）：同款显卡几秒完成，别的显卡需要 3–10 分钟。放在安装阶段做，是为了让第一次打开程序就是秒开，而不是让用户对着"正在加载引擎"发呆。

> **不要装到 `C:\Program Files`**。KataGo 需要把 GPU 调优缓存写进安装目录，受保护目录写不进去会导致每次启动重新调优。安装程序默认会避开它（F 盘 → D 盘 → 系统盘）。

**卸载**：开始菜单搜 GoDojo 右键卸载，或在「设置 → 应用」里找。会清掉程序、引擎、调优缓存，**保留 `games\` 里的棋谱**。

---

## 从源码运行

需要 Python 3.8+ 和一个 KataGo 可执行文件（引擎与权重不在本仓库，见下方"关于引擎"）。

```bash
git clone https://github.com/ericlu12138/GoGames.git
cd GoGames
```

**跑桌面版**

```bash
# 终端 A：起本地服务
python webapp/server.py

# 终端 B：开应用窗口
python webapp/app.py --debug
```

或者直接 `python webapp/app.py`，它会自己起服务再开窗口。

命令行参数：

| 参数 | 作用 |
|---|---|
| `--shell edge` | **默认**。用系统 Edge/Chrome 的应用模式开无边框窗口 |
| `--shell webview` | 用 pywebview 内嵌 WebView2（备选，见下方说明） |
| `--shell browser` | 用默认浏览器开一个标签页 |
| `--shell none` | 只跑本地服务，不开界面 |
| `--debug` | 开调试（Edge 外壳会同时打开开发者工具） |
| `--port 8800` | 固定端口（默认随机，只监听 `127.0.0.1`） |
| `--allow-multi` | 允许多开（默认禁止，因为会抢 GPU） |
| `--warmup` | 不开窗口、不启服务，只做引擎预热后退出 |

**跑原版**

```bash
python legacy/GoDojo.py
```

**改前端不用重启**：`webapp/web/` 里的文件是热加载的，改完刷新窗口即可。

### 关于外壳为什么用 Edge 应用模式

内嵌浏览器控件（pywebview + WebView2）理论上更"原生"，但它依赖 pythonnet 的 .NET 互操作。在开发机上实测：窗口能创建、WebView2 进程也起来了，但**页面渲染不出来**（内容区全黑），`evaluate_js` 返回 `None` —— 互操作层是坏的。

而系统自带的 Edge 渲染同一套前端完全正常。于是默认改用 Edge 应用模式：无地址栏无标签页、任务栏显示自己的图标、用独立 profile（`%LOCALAPPDATA%\GoDojoWeb\browser`）不动用户自己的浏览器配置、零额外依赖。

---

## 项目结构

```
GoGames/
├── webapp/                 桌面版 v2.0 源码
│   ├── core.py             围棋规则 Board + KataGo GTP 封装 Engine + 工具函数（无 GUI 依赖）
│   ├── server.py           本地 HTTP 服务 + 对局会话 + JSON API + 前端心跳
│   ├── app.py              桌面入口（单实例 / 引擎自愈 / 外壳选择 / 关窗清理）
│   ├── web/                前端：index.html + style.css + app.js + favicon
│   └── assets/             图标源文件
├── legacy/                 原版 tkinter 程序（保留，未改动）
│   ├── GoDojo.py
│   └── 启动围棋.bat
├── packaging/              打包与安装脚本
│   ├── GoDojo_dist.spec    PyInstaller 打包脚本
│   ├── GoDojo_setup.iss    Inno Setup 安装脚本
│   ├── build_payload.py    组装引擎/权重/配置成载荷
│   ├── make_icon.py        生成多尺寸图标
│   ├── sim_install.py      本地模拟安装
│   └── test_install.py     安装后端到端功能测试
├── tools/                  开发过程中的自对弈、复盘、调试脚本
├── docs/                   文档（使用说明、交接文档、复盘、训练方案）
└── games/                  对局记录（SGF + 分析数据 + 棋盘渲染图）
```

---

## 技术实现

### 架构

```
 应用窗口（Edge 应用模式 / 或内嵌 WebView2）
        │  fetch /api/state         每 250 ms 拉一次状态
        │  POST /api/play /api/new /api/undo ...
        │  POST /api/ping           每 2 s 心跳
        │  sendBeacon /api/quit     关窗时通知退出
        ▼
 本地 HTTP 服务（server.py，只监听 127.0.0.1，随机端口）
        │  对局会话：棋盘状态 + 规则校验 + 提子/打劫/SGF
        │  op_lock 串行化所有引擎调用
        ▼
 KataGo（gtp 模式子进程）
```

用 HTTP + 前端渲染代替原生控件，好处是界面能拿到完整的 CSS/Canvas 能力，改界面不用重新打包；代价是多了一层进程通信，因此所有状态查询都做成幂等的 `GET /api/state`。

### 踩过的坑与解法

这些都是实际调试中撞出来的，记在代码注释里：

| 问题 | 现象 | 解法 |
|---|---|---|
| **引擎调用并发** | 落子后软件"卡住"不动 | 评估线程和对局线程会抢 GTP 管道造成死锁，所有引擎调用一律串行加锁（`op_lock`） |
| **浏览器节流** | 窗口被遮挡时前端心跳停掉 | 关掉 `backgrounding-occluded-windows` / `renderer-backgrounding`；关窗判据也不用心跳，改成枚举系统窗口 |
| **未终局数目** | 显示 `B+198.5` 这种夸张比分 | 未终局时区域计分会失真，只信终局数子；中盘只看胜率和目差 |
| **GPU 首次调优** | 新显卡第一次启动像卡死 3.7 分钟 | 探测超时按引擎类型区分（OpenCL 给 15 分钟）；识别 stderr 里的 tuning 字样实时改进度；安装阶段预热 |
| **无独显机器** | 装完打不开 | 引擎候选按「配置 → OpenCL → CPU」逐个探测，谁先应答用谁，自动降级 |
| **进程早死仍等超时** | 降级要干等 40 秒 | `_probe` 每轮查进程是否已退出，立刻返回（降到 5.3 秒） |
| **黑终端窗口** | 打包后闪控制台 | PyInstaller `console=False`；代价是 `sys.stdout` 为 `None`，所有输出走自封装的 `say()` |
| **换候选时队列串台** | 读到上一轮引擎的输出 | 读线程与队列按轮次绑定传递，而不是共享全局 |

---

## 重新打包

```bash
# 1) 打包应用（需先建好带 PyInstaller 的虚拟环境）
pyinstaller --noconfirm --distpath dist --workpath build packaging/GoDojo_dist.spec

# 2) 组装载荷（把引擎、权重、配置铺进 dist）
python packaging/build_payload.py

# 3) 编译安装包（需安装 Inno Setup 6）
ISCC.exe packaging/GoDojo_setup.iss
```

改版本号：编辑 `packaging/GoDojo_setup.iss` 顶部的 `#define APP_VERSION`。

### 关于引擎

本仓库**不包含** KataGo 的二进制与权重（合计约 480 MB，且它们是第三方项目）。要自己跑，去下载：

- 引擎：<https://github.com/lightvector/KataGo/releases>
- 权重（`kata1` 系列）：<https://katagotraining.org/networks/>

然后把路径填进 `config.json`，或在程序里「设置 → 自动探测」。程序会在以下位置自动找引擎：

```
<程序目录>/KataGo-opencl/    <程序目录>/KataGo-cpu/
<程序目录>/engines/...       常见开发目录
```

---

## 已知限制

- **仅 Windows**。外壳依赖 Edge/Chromium 的应用模式，没有做跨平台。
- **没有代码签名**。Windows SmartScreen 会提示"未知发布者"，需要买证书（约 ¥1000/年）才能消除。
- **杀毒软件可能拦 `katago.exe`**（AI 推理程序容易被误判），报错了需要加白名单。
- **CPU 版跑 19 路建议 4 GB 以上空闲内存**。
- **未终局的胜负数字不可信**，见上方"踩过的坑"。
- 界面目前**全中文**。

---

## 致谢

- [**KataGo**](https://github.com/lightvector/KataGo) by David J Wu (lightvector) —— 本项目的全部棋力来源。引擎与官方权重均为 MIT 许可（见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)）。
- [KataGo Distributed Training](https://katagotraining.org/) —— 开源分布式训练项目，权重来自这里。
- [Sabaki](https://sabaki.yichuanshen.de/) —— 开发早期用它验证过 SGF 与 GTP 交互。

## 许可

本项目代码以 [MIT 许可](LICENSE) 发布。第三方组件许可见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。
