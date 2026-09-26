# -*- coding: utf-8 -*-
"""GoDojo Web 版 · 桌面入口

外壳策略(见 --shell):
  edge     默认。用系统已装的 Edge/Chrome 以「应用模式」开一个无边框窗口(--app=URL),
           看起来就是一个独立应用窗口,零额外依赖、渲染最可靠。
  webview  用 pywebview 内嵌 WebView2。理论上更"原生"(单进程),但依赖 pythonnet,
           在部分机器上会出现"窗口开了但内容空白"的情况,所以只作为备选。
  browser  用默认浏览器开一个标签页。
  none     只跑服务,不开界面。

另外做的事:
  · 单实例检测(避免多开抢 GPU)
  · 引擎路径失效时自动探测并写回 config.json
  · 前端心跳:窗口一关,后端自动退出并顺手清理 katago,不留僵尸进程
"""
import os
import sys
import time
import atexit
import argparse
import subprocess
import threading

# 让界面按原生分辨率渲染(否则高分屏下会被系统放大、边缘发虚)
try:
    import ctypes
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass

import server as srvmod
from core import (load_config, log, set_log_path, katago_processes,
                  kill_stale_engine, autofix_engine, detect_engine,
                  engine_candidates, Engine, base_dir)

MUTEX_NAME = "Global\\GoDojoWeb.SingleInstance.v1"
WINDOW_W, WINDOW_H = 1340, 910


# ---------------- 单实例 ----------------

def acquire_single_instance():
    """Windows 具名互斥体实现单实例。返回句柄(需全程持有);已有实例则返回 None。"""
    if os.name != "nt":
        return True
    import ctypes
    from ctypes import wintypes
    k32 = ctypes.windll.kernel32
    k32.CreateMutexW.restype = wintypes.HANDLE
    k32.CreateMutexW.argtypes = [wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR]
    h = k32.CreateMutexW(None, False, MUTEX_NAME)
    ERROR_ALREADY_EXISTS = 183
    if not h or k32.GetLastError() == ERROR_ALREADY_EXISTS:
        return None
    return h


def warn_already_running():
    msg = ("GoDojo 已经在运行了。\n\n"
           "同时开两个实例会让两个 katago 抢 GPU,两边都变慢,\n"
           "所以这里主动拦住了。\n\n"
           "确实要多开请加参数 --allow-multi 启动。")
    log("second instance blocked")
    try:
        import ctypes
        ctypes.windll.user32.MessageBoxW(None, msg, "GoDojo", 0x40)
    except Exception:
        print(msg)


# ---------------- 找浏览器 ----------------

BROWSER_CANDIDATES = [
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
]


def find_browser():
    """找一个能用应用模式的 Chromium 系浏览器"""
    for p in BROWSER_CANDIDATES:
        if os.path.exists(p):
            return p
    if os.name == "nt":
        try:
            import winreg
            for hive, sub in (
                (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\msedge.exe"),
                (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\chrome.exe"),
                (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\chrome.exe"),
            ):
                try:
                    with winreg.OpenKey(hive, sub) as k:
                        v = winreg.QueryValue(k, None)
                        if v and os.path.exists(v):
                            return v
                except Exception:
                    continue
        except Exception:
            pass
    return None


def browser_profile_dir():
    """独立 profile:不去碰用户自己的 Edge 配置,行为稳定、互不影响。
    注意:全新 profile 会触发 Edge 的「首次运行/登录引导」弹窗,
    所以这里预先放一个 First Run 标记文件把它压掉(Chromium 系认这个标记)。
    """
    base = os.environ.get("LOCALAPPDATA") or os.environ.get("TEMP") or "."
    d = os.path.join(base, "GoDojoWeb", "browser")
    try:
        os.makedirs(d, exist_ok=True)
        marker = os.path.join(d, "First Run")
        if not os.path.exists(marker):
            with open(marker, "w", encoding="utf-8"):
                pass
        dflt = os.path.join(d, "Default")
        os.makedirs(dflt, exist_ok=True)
    except Exception:
        pass
    return d


# 应用模式启动参数:
#   --app=URL              无地址栏无标签页,看起来就是个独立应用窗口
#   --user-data-dir        独立配置目录(配合上面的 First Run 标记)
#   --no-first-run 等      压掉首启引导/默认浏览器检查/后台联网
#   WebContentsForceDark   关掉"自动深色模式",否则浅色棋盘会被浏览器压暗
COMMON_FLAGS = [
    "--no-first-run",
    "--no-default-browser-check",
    "--no-service-autorun",
    "--disable-sync",
    "--disable-background-networking",
    "--disable-component-update",
    "--disable-extensions",
    # 下面三条很关键:窗口被别的窗口挡住时,Chromium 会限制/休眠后台渲染进程的定时器,
    # 会导致前端的"心跳"停掉。关掉这些节流,页面就一直保持活跃。
    "--disable-backgrounding-occluded-windows",
    "--disable-renderer-backgrounding",
    "--disable-ipc-flooding-protection",
    "--disable-features=WebContentsForceDark,Translate,"
    "msSleepingTabs,msEdgeSleepingTabs,msEdgeIdentityFeature,msEdgeSyncPromo,"
    "msImplicitSignin,msEdgeSigninPromo",
]


def screen_logical_size():
    """返回桌面可用工作区的「逻辑尺寸」(DIP) 与缩放系数。
    高分屏(比如 200% 缩放)下 --window-size 是按逻辑像素算的,
    如果还按物理分辨率给尺寸,窗口就会超出屏幕。这里先量再夹。
    """
    fallback = (1280.0, 800.0, 1.0)
    if os.name != "nt":
        return fallback
    try:
        import ctypes

        class R(ctypes.Structure):
            _fields_ = [("l", ctypes.c_long), ("t", ctypes.c_long),
                        ("r", ctypes.c_long), ("b", ctypes.c_long)]

        u32 = ctypes.windll.user32
        scale = 1.0
        try:
            dpi = u32.GetDpiForSystem()          # Win10 1607+
            if dpi:
                scale = dpi / 96.0
        except Exception:
            pass
        r = R()
        SPI_GETWORKAREA = 0x0030
        if u32.SystemParametersInfoW(SPI_GETWORKAREA, 0, ctypes.byref(r), 0):
            return ((r.r - r.l) / scale, (r.b - r.t) / scale, scale)
        return (u32.GetSystemMetrics(0) / scale, u32.GetSystemMetrics(1) / scale, scale)
    except Exception as e:
        log("量屏幕尺寸失败: %s" % e)
        return fallback


def find_app_windows():
    """列出当前系统里"看起来是 GoDojo 主窗口"的可见窗口标题。

    用它来判断用户有没有关掉窗口 —— 比依赖前端心跳可靠得多:
    浏览器的定时器会因为窗口被遮挡/休眠而被节流,但窗口在不在是系统级事实。
    """
    if os.name != "nt":
        return []
    try:
        import ctypes
        from ctypes import wintypes
        u32 = ctypes.windll.user32
        out = []

        def cb(h, _):
            if not u32.IsWindowVisible(h):
                return True
            n = u32.GetWindowTextLengthW(h)
            if n <= 0:
                return True
            buf = ctypes.create_unicode_buffer(n + 2)
            u32.GetWindowTextW(h, buf, n + 2)
            t = buf.value
            if "GoDojo" not in t:
                return True
            r = (ctypes.c_long * 4)()
            u32.GetWindowRect(h, ctypes.byref(r))
            if r[2] - r[0] > 300 and r[3] - r[1] > 300:      # 排除提示条之类的小窗
                out.append(t)
            return True

        W = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
        u32.EnumWindows(W(cb), 0)
        return out
    except Exception as e:
        log("枚举窗口失败: %s" % e)
        return ["(枚举失败)"]          # 出错时不要误判成"窗口已关闭"


# ---------------- 主流程 ----------------

def say(msg):
    """往控制台写字,但绝不让它拖垮程序。

    exe 是 --windowed 打包的,没有控制台时 sys.stdout 是 None,裸 print()
    会抛 AttributeError。--warmup 由安装程序调用时也走这条路,所以统一
    用这个函数,并且顺手写进日志(安装时用 runhidden,用户看不到 stdout)。
    """
    log(msg)
    try:
        if sys.stdout is not None:
            sys.stdout.write(msg + "\n")
            sys.stdout.flush()
    except Exception:
        pass


def run_warmup(args):
    """引擎预热:把 GPU 的首次调优在安装阶段就做掉

    为什么需要:
      KataGo 的 OpenCL 版第一次使用某块显卡时,要现场编译/试跑各种内核
      配置来挑最快的一组,耗时 5-10 分钟(取决显卡)。若等到用户第一次
      开软件时才做,会看到"卡住不动",体验极差。

    做法:
      不启 HTTP 服务、不开窗口,直接构造 Engine(它会按候选逐个试,
      OpenCL 版探测超时给足 15 分钟)。成功后立刻退出 —— 调优结果已经
      落在引擎目录的 KataGoData\\opencltuning 里,以后启动秒开。

    退出码:
      0  预热成功(或本来就有缓存,很快返回)
      1  预热失败(安装程序据此提示,但不阻断安装)
    """
    cfg = load_config()
    set_log_path(cfg.get("paths", {}).get("log"))
    log("=== GoDojo 引擎预热开始 ===")
    say("GoDojo 引擎预热:正在为显卡做首次调优,约 5-10 分钟(仅首次)...")
    say("这一步做完,以后每次打开软件都是秒开。请勿关闭此窗口。")
    say("安装目录: %s" % base_dir())

    cands = [c["label"] for c in engine_candidates(cfg)]
    say("候选引擎: %s" % (", ".join(cands) if cands else "(未找到)"))
    if not cands:
        log("warmup: 没找到可用引擎")
        return 1

    t0 = time.time()
    eng = Engine(cfg)                # 构造过程就是探测 + 调优
    el = time.time() - t0
    ok = bool(eng.ok)
    if ok:
        say("\n预热完成 (%.0f 秒),实际使用引擎: [%s]" % (el, eng.label))
        say("现在打开 GoDojo 就是秒启动。")
        log("warmup ok [%s] in %.0fs" % (eng.label, el))
    else:
        say("\n预热未成功(%.0f 秒): %s" % (el, eng.err))
        say("不影响安装 —— 软件启动时会自动重试,也可以改用 CPU 引擎。")
        log("warmup failed: %s" % eng.err)
    eng.shutdown()
    # 落一个结果文件:exe 是 --windowed 打包的,没有控制台时安装程序拿不到
    # 标准输出,只能靠这个文件判断预热结果。
    try:
        with open(os.path.join(base_dir(), "warmup.result"), "w",
                  encoding="utf-8") as f:
            f.write("ok=%d\nengine=%s\nseconds=%.0f\n%s\n"
                    % (1 if ok else 0, eng.label, el,
                       eng.err if not ok else ""))
    except Exception:
        pass
    return 0 if ok else 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=0)
    ap.add_argument("--debug", action="store_true")
    ap.add_argument("--shell", choices=["auto", "edge", "webview", "browser", "none"], default="auto")
    ap.add_argument("--webview", action="store_true", help="等同于 --shell webview")
    ap.add_argument("--browser", action="store_true", help="等同于 --shell browser")
    ap.add_argument("--no-window", action="store_true", help="只是 --shell none 的别名")
    ap.add_argument("--allow-multi", action="store_true")
    ap.add_argument("--warmup", action="store_true",
                    help="只做引擎预热(GPU 首次调优)后退出,供安装程序调用")
    ap.add_argument("--warmup-timeout", type=int, default=1800,
                    help="预热最长等待秒数(默认 1800)")
    args = ap.parse_args()

    if args.warmup:
        return run_warmup(args)

    cfg = load_config()
    set_log_path(cfg.get("paths", {}).get("log"))
    log("=== GoDojo Web 启动 (frozen=%s, shell=%s) ===" % (getattr(sys, "frozen", False), args.shell))
    # 回归检查:把关键路径写进日志,便于发现"配置没生效 / 棋谱写错目录"这类问题
    log("paths: games=%s | external=%s | log=%s" % (
        cfg.get("paths", {}).get("games"), cfg.get("paths", {}).get("external"),
        cfg.get("paths", {}).get("log")))

    fixed, notes = autofix_engine(cfg)
    for n in notes:
        log("engine note: " + n)
    if not detect_engine(cfg)["found"]:
        log("警告:没有找到可用的 KataGo 引擎")

    holder = True
    if not args.allow_multi:
        holder = acquire_single_instance()
        if holder is None:
            warn_already_running()
            return 2

    stale = katago_processes()
    if stale:
        log("检测到 %d 个已存在的 katago 进程: %s" % (len(stale), stale))

    srvmod.reset_heartbeat()
    server, port, _ = srvmod.start_server(cfg, port=args.port or None)
    url = "http://127.0.0.1:%d/" % port

    def cleanup():
        try:
            sess = srvmod.Handler.session
            if sess and sess.engine:
                sess.engine.shutdown()      # 拿不到锁就直接 kill,绝不等 genmove
            log("引擎已清理")
        except Exception as e:
            log("cleanup err %s" % e)
        try:
            server.shutdown()
        except Exception:
            pass

    atexit.register(cleanup)

    shell = args.shell
    if args.no_window:
        shell = "none"
    elif args.webview:
        shell = "webview"
    elif args.browser:
        shell = "browser"
    if shell == "auto":
        shell = "edge" if find_browser() else "browser"

    if shell == "none":
        print("服务已启动: %s" % url)
        print("按 Ctrl+C 退出(或调用 POST /api/quit)")
        try:
            while not srvmod.quit_requested():
                time.sleep(1)
        except KeyboardInterrupt:
            pass
        cleanup()
        return 0

    if shell == "browser":
        import webbrowser
        webbrowser.open(url)
        print("已在浏览器打开: %s" % url)
        try:
            while heartbeat_age_wait():
                pass
        except KeyboardInterrupt:
            pass
        cleanup()
        return 0

    if shell == "webview":
        return run_webview(args, url, cleanup)

    return run_edge_app(url, cleanup, args.debug)


def heartbeat_age_wait(limit=20.0):
    """等心跳:窗口关了(心跳断了)或前端主动点退出,就返回 False 结束"""
    age = srvmod.heartbeat_age()
    if srvmod.quit_requested():
        return False
    if age is None:
        return True                 # 还没连上,继续等
    return age <= limit


def run_edge_app(url, cleanup, debug):
    """用 Edge/Chrome 的应用模式开一个无边框窗口 —— 看起来就是个独立应用"""
    exe = find_browser()
    if not exe:
        log("没找到 Edge/Chrome,退回默认浏览器")
        import webbrowser
        webbrowser.open(url)
        try:
            while heartbeat_age_wait():
                time.sleep(2)
        except KeyboardInterrupt:
            pass
        cleanup()
        return 0

    prof = browser_profile_dir()
    sw, sh, scale = screen_logical_size()
    ww = int(min(WINDOW_W, sw * 0.94))
    wh = int(min(WINDOW_H, sh * 0.93))
    log("屏幕工作区 %.0fx%.0f DIP(缩放 %.0f%%),窗口取 %dx%d"
        % (sw, sh, scale * 100, ww, wh))
    cmd = [exe, "--app=" + url, "--user-data-dir=" + prof] + COMMON_FLAGS + [
        "--window-size=%d,%d" % (ww, wh),
    ]
    if debug:
        cmd.append("--auto-open-devtools-for-tabs")
    log("launching app window: %s" % exe)
    log("  args: %s" % " ".join(cmd[1:]))
    try:
        proc = subprocess.Popen(cmd)
    except Exception as e:
        log("启动浏览器失败: %s,退回默认浏览器" % e)
        import webbrowser
        webbrowser.open(url)
        proc = None

    started = time.time()
    loaded = False
    quit_by_user = False
    gone = 0
    try:
        while True:
            time.sleep(2)

            # 1) 前端主动退出(点了「退出」按钮,或窗口关闭时 beforeunload 发的信标)
            if srvmod.quit_requested():
                log("收到退出信号(前端点了退出 / 窗口正在关闭)")
                quit_by_user = True
                break

            # 2) 还没确认前端连上时,以"窗口出现或收到心跳"为准
            if not loaded:
                if srvmod.heartbeat_age() is not None or find_app_windows():
                    loaded = True
                    log("前端已连接(窗口已渲染)")
                elif time.time() - started > 45:
                    log("等待窗口/前端超时,退出")
                    break
                continue

            # 3) 已加载:靠"系统里这个窗口还在不在"判断用户是否关掉了它。
            #    不用心跳做判据 —— 窗口被遮挡时浏览器的定时器会被节流,会误判。
            if find_app_windows():
                gone = 0
            else:
                gone += 1
                if gone >= 2:
                    log("应用窗口已关闭,退出后端")
                    break

            # 4) 兜底:浏览器进程本身退出了
            if proc is not None and proc.poll() is not None:
                log("浏览器进程已退出")
                break
    except KeyboardInterrupt:
        quit_by_user = True
    # 用户点了「退出」:直接把应用窗口关掉,不用他自己再关一次
    if quit_by_user and proc is not None:
        try:
            if proc.poll() is None:
                proc.terminate()
                time.sleep(1.0)
                if proc.poll() is None:
                    proc.kill()
            log("已关闭应用窗口")
        except Exception as e:
            log("关闭窗口失败: %s" % e)
    cleanup()
    return 0


def run_webview(args, url, cleanup):
    """pywebview 内嵌 WebView2(备选外壳)"""
    try:
        import webview
    except Exception as e:
        log("pywebview 导入失败: %s,退回默认浏览器" % e)
        import webbrowser
        webbrowser.open(url)
        try:
            while heartbeat_age_wait():
                time.sleep(2)
        except KeyboardInterrupt:
            pass
        cleanup()
        return 1

    # WebView2 只加载 127.0.0.1 的本地页面,显式关掉代理
    os.environ["WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS"] = "--no-proxy-server"

    icon = None
    for cand in ("assets/godogo.ico", "godogo.ico"):
        p = os.path.join(getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__))), cand)
        if os.path.exists(p):
            icon = p
            break

    win = webview.create_window(
        "GoDojo · 围棋陪练", url,
        width=WINDOW_W, height=WINDOW_H, min_size=(1000, 700),
        background_color="#14161a", text_select=False)

    def _evt(name):
        def h(*a, **kw):
            log("window event: %s" % name)
        return h

    for ev in ("shown", "loaded", "loading", "closed"):
        try:
            getattr(win.events, ev).__iadd__(_evt(ev))
        except Exception:
            pass

    def probe():
        """启动后自检:能读到 DOM 说明内嵌渲染正常;读不到就提示换外壳"""
        time.sleep(8)
        try:
            v = win.evaluate_js("JSON.stringify({t:document.title,r:document.readyState,"
                                "st:(document.getElementById('status')||{}).textContent||null})")
        except Exception as e:
            v = "exception: %r" % e
        log("PROBE dom=%s" % v)
        if not v or v == "null" or str(v).startswith("exception"):
            log("!! 内嵌 WebView 未正常渲染 —— 请改用 --shell edge(默认外壳)")
            try:
                win.destroy()
            except Exception:
                pass

    log("opening webview window: %s" % url)
    webview.start(probe, gui="edgechromium", debug=args.debug)
    cleanup()
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main() or 0)
    except Exception as e:
        import traceback
        log("fatal: %s\n%s" % (e, traceback.format_exc()))
        try:
            import ctypes
            ctypes.windll.user32.MessageBoxW(None, "启动失败:\n%s" % e, "GoDojo", 0x10)
        except Exception:
            print("启动失败: %s" % e)
        sys.exit(1)
