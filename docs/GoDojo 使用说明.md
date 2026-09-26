# GoDojo · 围棋陪练(桌面版)使用说明

**版本**：2.0(Web UI 桌面版)
**形态**：免安装绿色版 + 可选一键安装
**体积**：约 18 MB(不含引擎与权重)

---

## 一、这是什么

把原来的 `GoDojo.py`(tkinter 版)**重做成了 Web 界面的桌面程序**:界面用 HTML/Canvas 渲染,外面套一个无边框应用窗口,再用 PyInstaller 打成单个 exe。

与旧版对照:

| | 旧版(tkinter) | 新版(Web 桌面版) |
|---|---|---|
| 启动 | 需装 Python,双击 `启动围棋.bat` | **双击 `GoDojo.exe`**,不需要 Python |
| 界面 | tkinter 原生控件 | HTML/CSS + Canvas,按设备像素比渲染,高分屏清晰 |
| 窗口 | 会闪控制台窗口 | 无控制台,无地址栏,像个独立应用 |
| 图标 | 无 | 有(木纹棋盘 + 黑白子,6 个尺寸) |
| 多开 | 互相抢 GPU 导致极慢 | **自动拦截第二个实例** |
| 关窗 | 引擎进程可能残留 | 关窗自动退出并清理 katago |
| 引擎路径 | 硬编码在代码里 | 外置于 `config.json`,界面可改、可自动探测 |
| 核心逻辑 | `GoDojo.py` | `webapp/core.py`(规则与引擎封装**原样搬过来**,没重写) |

旧版 `GoDojo.py` 和 `启动围棋.bat` **都还保留着、没有被改动**,可以继续用。

---

## 二、怎么启动

**方式 1:直接双击**
```
F:\围棋\发布\GoDojo\GoDojo.exe
```
首次启动约 5–10 秒加载引擎(KataGo 权重 201 MB),界面上会显示"正在加载引擎"。

**方式 2:装成正式程序(开始菜单 + 桌面图标 + 可卸载)**
在 `GoDojo` 文件夹上右键 → 在终端中打开:
```powershell
powershell -ExecutionPolicy Bypass -File .\install.ps1
```
之后在「设置 → 应用 → 已安装的应用」里能看到并卸载 `GoDojo 围棋陪练`。

**方式 3:命令行参数**(排查问题或特殊用法)

| 参数 | 作用 |
|---|---|
| `--shell edge` | **默认**。用系统 Edge/Chrome 的应用模式开无边框窗口 |
| `--shell webview` | 用 pywebview 内嵌 WebView2(备选,见第七节) |
| `--shell browser` | 用默认浏览器开一个标签页 |
| `--shell none` | 只跑本地服务,不开界面 |
| `--debug` | 开调试(Edge 外壳会同时打开开发者工具) |
| `--port 8800` | 固定端口(默认随机,只监听 127.0.0.1) |
| `--allow-multi` | 允许多开(默认禁止,因为会抢 GPU) |

---

## 三、界面说明

**顶栏**:棋盘(9/13/19) · 你执(黑/白) · 对手(内置 KataGo / 外接 AI / AI 对 AI) · 让子(0/2/3/4/5) · 强度滑块 · 操作按钮
> 改「棋盘 / 你执 / 对手 / 让子」会**立刻开新局**。

**按钮**:新局 · 悔棋 · 提示 · 停一手 · 分析 · 认输 · 保存棋谱 · ⚙(设置) · ⏻(退出程序)

**右侧面板**
- **状态行**:谁在走、引擎状态、出错原因(绿色=正常、橙色=进行中、红色=出错)
- **胜率条**:用目差换算(不是引擎的胜率头 —— KataGo 在小棋盘上没校准)
- **引擎候选点**:前 5 个候选 + 各自目差 + 访问次数,以及主变(PV)
- **对局记录**:逐手着法 + 提子数
- **讲评**:每手走完自动评价,掉胜率多会标出来并给推荐点

**棋盘上**:最后一手画红圈 · 最近 12 手带手数 · 悬停有半透明预览子 · 「提示」画 A/B/C 推荐点

**快捷键**(焦点不在输入框时)

| 键 | 作用 |
|---|---|
| `Z` / `U` | 悔棋 |
| `H` | 提示 |
| `P` | 停一手 |
| `A` | 分析 |
| `N` | 新局 |

---

## 四、三种对手模式

| 模式 | 说明 |
|---|---|
| **内置 KataGo** | 本机引擎直接应手,正常下棋用这个 |
| **外接 AI(文件)** | 你下完,程序把局面写到 `F:\围棋\外接AI\position.txt`,等外部 AI 把坐标写进 `ai_move.txt`。协议见同目录 `协议_给外接AI.md` |
| **AI 对 AI(双文件)** | 黑白分别读 `black_move.txt` / `white_move.txt`,可以挂两个不同的 AI 互相下 |

---

## 五、设置(顶栏 ⚙)

- **katago.exe / 权重 / 配置文件**:可填绝对路径,也可填相对程序目录的相对路径
- **自动探测**:在程序目录、`F:\围棋\KataGo-opencl`、`KataGo-cpu` 等常见位置找引擎
- **重启引擎**:引擎卡死或崩溃时不用重启整个程序
- **清理残留 katago**:强制结束所有 `katago.exe`(若同时开着旧版 GoDojo,会连它的引擎一起杀掉,所以默认不自动执行)

设置存在 `config.json`,**改完立即生效并写回文件**。

> 路径有兜底:配置里的引擎路径失效时,启动会自动探测可用引擎并写回配置,换机器一般不用手改。

---

## 六、常见问题

**Q:一直显示"正在加载引擎"?**
引擎加载要 5–10 秒。超过 30 秒还没好,点 ⚙ → 自动探测 → 保存并应用 → 重启引擎,或看日志。

**Q:日志在哪?**
`F:\围棋\发布\GoDojo\godojo_web.log`(路径也写在 `config.json` 的 `paths.log`)。

**Q:提示"GoDojo 已经在运行了"?**
单实例保护。同时开两个会让两个 katago 抢 GPU、两边都变慢。确实要多开就加 `--allow-multi`。

**Q:胜负数字很夸张(比如 B+198.5)?**
**未终局**的局面用区域计分会被放大到没有意义(旧版同样如此)。中盘只能看**胜率**和**目差**,要精确数目必须下到终局。

**Q:下着下着卡住了?**
点 ⚙ → 重启引擎。若无效,点「清理残留 katago」再重启引擎。

**Q:关掉窗口后,后台还在跑吗?**
不会。关窗时会自动退出后端并结束 katago。想主动退出可以点顶栏右端的 ⏻。

**Q:棋盘颜色怎么变暗了 / 变得不像木纹?**
Edge 的「自动深色模式」会篡改网页配色,程序已经用 `color-scheme` 和启动参数关掉了它。若仍异常,检查 Edge 设置 → 外观 → 自动深色模式。

---

## 七、关于外壳:为什么默认用 Edge 应用模式

内嵌浏览器控件(pywebview + WebView2)理论上更"原生"(单进程、真正的原生窗口),但**它依赖 pythonnet 的 .NET 互操作**。在你这台机器上实测:窗口能创建、WebView2 进程也起来了,但**页面渲染不出来**(内容区全黑),`evaluate_js` 也返回 `None` —— 互操作层是坏的。

而系统自带的 Edge 渲染同一套前端完全正常。所以默认改用 **Edge 应用模式**:
- 无地址栏、无标签页,视觉上就是独立应用窗口
- 任务栏/标题栏显示 GoDojo 自己的图标(通过 favicon)
- 用独立 profile(`%LOCALAPPDATA%\GoDojoWeb\browser`),不动你自己的浏览器配置
- 零额外依赖,不需要 Node 也不需要 Rust

想试内嵌方式:`GoDojo.exe --shell webview`,它会自己探测并在渲染失败时提示。

---

## 八、目录结构

```
F:\围棋\发布\GoDojo\
├── GoDojo.exe          ← 主程序
├── _internal\          ← 运行库(Python 3.8 + pywebview + WebView2 组件 + 打包版前端,勿删勿动)
├── web\                ← 前端资源(放在外面,改界面不用重新打包)
├── config.json         ← 配置(引擎路径、默认棋盘、日志位置)
├── install.ps1         ← 安装到开始菜单/桌面
├── uninstall.ps1       ← 卸载
├── 使用说明.md          ← 本文件
└── godojo_web.log      ← 运行日志(首次运行后生成)
```

**源码**(想改的话)在 `F:\围棋\webapp\`:
```
webapp\
├── core.py      围棋规则 Board + KataGo GTP 封装 Engine + 工具函数(无 GUI 依赖)
├── server.py    本地 HTTP 服务 + 对局会话 + JSON API + 前端心跳
├── app.py       桌面入口(单实例 / 引擎自愈 / 外壳选择 / 关窗清理)
├── web\         前端:index.html + style.css + app.js + favicon.ico
└── assets\      图标
```

**改前端不用重新打包**:直接改 `发布\GoDojo\web\` 里的文件,刷新窗口即可。程序优先加载 exe 旁边这个 `web\`,找不到才用打包在 `_internal` 里的那份。

**改了 Python 代码**才需要重新打包:
```powershell
cd D:\GoDojoBuild
D:\GoDojoBuild\venv\Scripts\python.exe -m PyInstaller --noconfirm --clean --onedir --windowed ^
  --name GoDojo --icon "F:\围棋\webapp\assets\godogo.ico" ^
  --add-data "F:\围棋\webapp\web;web" --add-data "F:\围棋\webapp\assets;assets" ^
  --paths "F:\围棋\webapp" --hidden-import webview.platforms.edgechromium ^
  --hidden-import webview.platforms.winforms "F:\围棋\webapp\app.py"
```

调试源码(不用打包,改完刷新即可):
```powershell
# 终端 A:起服务
D:\Anaconda3\python.exe F:\围棋\webapp\server.py
# 终端 B:开窗口
D:\GoDojoBuild\venv\Scripts\python.exe F:\围棋\webapp\app.py --debug
```

---

## 九、原理简图

```
 应用窗口(Edge 应用模式 / 或内嵌 WebView2)
        │  fetch /api/state         每 250ms 拉一次状态
        │  POST /api/play /api/new /api/undo ...
        │  POST /api/ping           每 2s 心跳
        │  sendBeacon /api/quit     关窗时通知退出
        ▼
 本地 HTTP 服务(server.py,只监听 127.0.0.1,随机端口)
        │  对局会话:棋盘状态 + 规则校验 + 提子/打劫/SGF
        │  op_lock 串行化所有引擎调用
        ▼
 KataGo(gtp 模式子进程)
```

引擎调用一律串行加锁 —— 这是旧版踩过的坑(评估线程和对局线程抢 GTP 管道会死锁,现象是"落子后卡住"),新版沿用同一套锁。

**关窗清理**:后端每 2 秒枚举一次系统窗口,发现 GoDojo 窗口没了就退出并结束 katago。之所以不用前端心跳当判据,是因为浏览器在窗口被遮挡时会节流定时器,会造成误判(这个坑已经踩过并修掉了)。
