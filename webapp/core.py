# -*- coding: utf-8 -*-
"""GoDojo Web 版 · 核心逻辑(无 GUI 依赖)

从 GoDojo.py 抽出的可复用部分:
  - Board        围棋规则(提子 / 自杀 / 打劫禁全局同形 / SGF)
  - Engine       KataGo GTP 封装(串行加锁,后台线程读输出)
  - 工具函数     parse_info / disp_wr / handicap_points

与 server.py(HTTP 服务)、app.py(pywebview 外壳)共用,不 import tkinter。
"""
import os
import re
import sys
import json
import math
import time
import queue
import threading
import datetime
import subprocess

LETTERS = "ABCDEFGHJKLMNOPQRST"
COLS = LETTERS

# 隐藏子进程控制台窗口(Windows):不加这个,每次 tasklist / katago 启动
# 都会闪一个黑色终端窗口,十分吓人。非 Windows 平台取 0 即可。
_NO_WINDOW = 0x08000000 if os.name == "nt" else 0

# 开发机上的引擎固定位置(兜底用)。
# 绿色版(发布\GoDojo\)不带引擎,靠这个回退到 F 盘根目录的引擎 —— 与
# detect_engine() 里的兜底保持一致。分发安装版不会命中(安装目录自带引擎)。
FALLBACK_ENGINE_ROOT = r"F:\围棋" if os.name == "nt" else ""

# ---------------- 配置 ----------------

DEFAULT_CONFIG = {
    "engine": {
        "katago": "KataGo-opencl/katago.exe",
        "model": "KataGo-opencl/kata1-tf3-b11c768-s11500M-d6163M.bin.gz",
        "config": "KataGo-opencl/gtp_practice.cfg"
    },
    "paths": {
        "games": "games",
        "external": "外接AI",
        "log": "godojo_web.log"
    },
    "game": {
        "size": 19,
        "human": "B",
        "handicap": 0,
        "visits": 120,
        "komi": 7.5
    },
    "startup": {
        "killStaleEngine": False
    },
    "server": {
        "host": "127.0.0.1",
        "port": 0
    }
}


def base_dir():
    """配置与资源的基准目录。
    源码运行 -> 项目根(webapp 的上一级);打包运行 -> exe 所在目录。
    """
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def config_path():
    return os.path.join(base_dir(), "config.json")


def _deep_merge(dst, src):
    """用户配置(src)覆盖默认值(dst);键不存在时才由默认值补齐"""
    for k, v in src.items():
        if isinstance(v, dict) and isinstance(dst.get(k), dict):
            _deep_merge(dst[k], v)
        else:
            dst[k] = v                # 用户配置优先
    return dst


def load_config(save_if_missing=True):
    """读 config.json(缺字段用默认值补齐);相对路径以 base_dir 为基准展开。"""
    cfg = json.loads(json.dumps(DEFAULT_CONFIG))
    p = config_path()
    if os.path.exists(p):
        try:
            with open(p, encoding="utf-8-sig") as f:
                _deep_merge(cfg, json.load(f))
        except Exception:
            pass
    elif save_if_missing:
        try:
            save_config(cfg)
        except Exception:
            pass
    root = base_dir()
    for group in ("engine", "paths"):
        for k, v in cfg.get(group, {}).items():
            if isinstance(v, str) and v and not os.path.isabs(v):
                cfg[group][k] = os.path.normpath(os.path.join(root, v))
    return cfg


def save_config(cfg):
    """写 config.json —— 一律 UTF-8 无 BOM(引擎侧的 cfg 加 BOM 会解析失败,这里保持同一习惯)"""
    data = json.dumps(cfg, ensure_ascii=False, indent=2)
    with open(config_path(), "w", encoding="utf-8", newline="\n") as f:
        f.write(data)


_LOGF = {"path": None}


def log(msg, path=None):
    p = path or _LOGF["path"]
    if not p:
        return
    try:
        with open(p, "a", encoding="utf-8") as f:
            f.write("%s %s\n" % (datetime.datetime.now().strftime("%H:%M:%S"), msg))
    except Exception:
        pass


def set_log_path(p):
    _LOGF["path"] = p


# ---------------- 工具函数 ----------------

def disp_wr(lead, size):
    """用目差换算"展示用胜率":9 路 1 目价值大,19 路 1 目价值小。
    KataGo 的胜率头在小棋盘上未校准,所以这里统一用目差换算,保证三个棋盘尺寸都可读。
    """
    if lead is None:
        return None
    scale = 1.2 if size <= 9 else (2.5 if size <= 13 else 6.0)
    return 1.0 / (1.0 + math.exp(-lead / scale))


def handicap_points(size, n):
    """返回让 n 子的坐标列表 [(i, j)](i 为列,j=0 为最上一行)"""
    if size == 9:
        hoshi = [(2, 2), (6, 6)]                      # C7, G3(对角)
        center = (4, 4)                               # E5
        corners = [(2, 2), (6, 6), (2, 6), (6, 2)]    # C7 G3 C3 G7
    else:
        hoshi = [(15, 3), (3, 15)]                    # Q16, D4
        center = (9, 9)                               # K10
        corners = [(15, 3), (3, 15), (3, 3), (15, 15)]
    if n <= 2:
        return hoshi[:n]
    if n == 3:
        return hoshi + [center]
    if n == 4:
        return corners
    return corners + [center]


def parse_info(infos):
    """解析 kata-analyze / kata-genmove_analyze 的 info 行"""
    if not infos:
        return None

    def segs_of(line):
        out = []
        for seg in line.split("info move ")[1:]:
            mv = seg.split()[0]
            if not (mv and mv[0] in LETTERS):
                continue
            w = re.search(r"\bwinrate\s+([0-9.]+)", seg)
            s = re.search(r"\bscoreLead\s+(-?[0-9.]+)", seg)
            v = re.search(r"\bvisits\s+(\d+)", seg)
            wr = float(w.group(1)) if w else None
            if wr is not None and wr > 1.0001:
                wr = None
            out.append({
                "move": mv,
                "winrate": wr,
                "scoreLead": float(s.group(1)) if s else None,
                "visits": int(v.group(1)) if v else 0,
            })
        return out

    # 取"最后一条包含多个候选"的行 = 搜索最充分的那次报告
    best_line, cands = None, []
    for line in reversed(infos):
        c = segs_of(line)
        if len(c) >= 2:
            best_line, cands = line, c
            break
    if best_line is None:
        best_line = infos[-1]
        cands = segs_of(best_line)

    out = {"winrate": None, "scoreLead": None, "pv": "", "cands": cands}
    if cands:
        out["winrate"] = cands[0]["winrate"]
        out["scoreLead"] = cands[0]["scoreLead"]
    if out["winrate"] is None:
        m = re.search(r"\bwinrate\s+([0-9.]+)", best_line)
        if m and float(m.group(1)) <= 1.0001:
            out["winrate"] = float(m.group(1))
    if out["scoreLead"] is None:
        m = re.search(r"\bscoreLead\s+(-?[0-9.]+)", best_line)
        if m:
            out["scoreLead"] = float(m.group(1))
    m = re.search(r"\bpv\s+((?:[A-T][0-9]{1,2}\s*)+)", best_line)
    if m:
        out["pv"] = m.group(1).strip()
    return out


def katago_processes():
    """列出正在运行的 katago 进程(用于提示残留 / 一键清理)"""
    if os.name != "nt":
        return []
    # tasklist 输出跟随系统 ANSI 代码页(中文系统是 GBK),
    # 显式按 GBK 解码,避免在 UTF-8 模式的 Python 里抛 UnicodeDecodeError
    try:
        r = subprocess.run(["tasklist", "/FI", "IMAGENAME eq katago.exe", "/FO", "CSV", "/NH"],
                           capture_output=True, timeout=15, creationflags=_NO_WINDOW)
        out = r.stdout.decode("gbk", errors="replace")
    except Exception:
        return []
    procs = []
    for line in out.splitlines():
        parts = [x.strip('"') for x in line.split('","')]
        if len(parts) >= 2 and parts[0].lower().startswith("katago"):
            procs.append({"name": parts[0], "pid": parts[1]})
    return procs


def kill_stale_engine():
    """强制结束所有 katago.exe(会连带杀掉别的 GoDojo 实例的引擎,故默认不自动执行)"""
    try:
        r = subprocess.run(["taskkill", "/F", "/IM", "katago.exe"],
                           capture_output=True, text=True, timeout=20, creationflags=_NO_WINDOW)
        return r.returncode == 0, (r.stdout + r.stderr).strip()
    except Exception as e:
        return False, str(e)


def engine_candidates(cfg):
    """按优先级列出"可用的引擎组合",供启动时逐个尝试。

    顺序:配置文件指定的 -> 安装目录的 OpenCL(GPU)版 -> 安装目录的 CPU 版。
    每项 = {katago, model, config, label}。分发版带双引擎,GPU 不可用时自动降级。
    """
    eng = cfg.get("engine", {})
    root = base_dir()
    out, seen = [], set()

    def find_model(engine_dir):
        """权重查找:引擎目录 -> 同级 -> models/ -> 安装根及其它引擎目录

        分发版里权重只放一份(共享),任何一层能命中就行,不必每个引擎目录都塞 200MB。
        """
        par = os.path.dirname(engine_dir)                  # engines/ 或安装根
        gran = os.path.dirname(par)                        # 安装根
        dirs = [engine_dir, par, os.path.join(par, "models"), gran]
        for sub in ("models", "KataGo-opencl", "KataGo-cpu", "engines", "engines/models"):
            dirs.append(os.path.join(gran, sub))
        seen_dir = set()
        for d in dirs:
            if d in seen_dir:
                continue
            seen_dir.add(d)
            try:
                cands = [os.path.join(d, f) for f in sorted(os.listdir(d))
                         if f.endswith(".bin.gz")]
            except Exception:
                cands = []
            for c in cands:
                if os.path.isfile(c):
                    return c
        return None

    def find_cfg(engine_dir):
        """引擎配置查找:优先本目录,再上层,最后借用另一个引擎目录的配置

        配置是通用的(build 时把 logDir/权重路径都写成相对/注释掉了),
        所以 CPU 版借 OpenCL 版的 gtp_web.cfg 完全没问题。
        """
        par = os.path.dirname(engine_dir)
        gran = os.path.dirname(par)
        dirs = [engine_dir, par, gran, root, os.path.join(root, "engines")]
        for sub in ("KataGo-opencl", "KataGo-cpu"):
            dirs.append(os.path.join(gran, sub))
            dirs.append(os.path.join(root, sub))
            dirs.append(os.path.join(root, "engines", sub))
        seen_d = set()
        for d in dirs:
            if d in seen_d:
                continue
            seen_d.add(d)
            for cf in ("gtp_web.cfg", "gtp_practice.cfg", "gtp_play.cfg"):
                p = os.path.join(d, cf)
                if os.path.isfile(p):
                    return p
        return None

    def add(k, m, c, label):
        if not (k and m and c):
            return
        if not (os.path.isfile(k) and os.path.isfile(m) and os.path.isfile(c)):
            return
        key = os.path.normcase(os.path.abspath(k))
        if key in seen:
            return
        seen.add(key)
        out.append({"katago": k, "model": m, "config": c, "label": label})

    add(eng.get("katago"), eng.get("model"), eng.get("config"), "配置指定")

    # 搜索范围:安装目录、安装目录/engines、以及开发机上的固定位置
    # (后者是给"绿色版放在 F:\围棋\发布\GoDojo、引擎在 F:\围棋\KataGo-*"这种
    #  老布局兜底的 —— 和 detect_engine 里的兜底保持一致)
    scopes = [(root, ""), (os.path.join(root, "engines"), "")]
    if FALLBACK_ENGINE_ROOT and os.path.isdir(FALLBACK_ENGINE_ROOT):
        # 兜底项排最后,标签加"(外部)"以便和安装目录里的引擎区分
        scopes.append((FALLBACK_ENGINE_ROOT, "(外部)"))
    tried = set()
    for rel, base_label in (("KataGo-opencl", "OpenCL(GPU)"), ("KataGo-cpu", "CPU")):
        for scope, suf in scopes:
            d = os.path.join(scope, rel)
            if d in tried:
                continue
            tried.add(d)
            k = os.path.join(d, "katago.exe")
            if not os.path.isfile(k):
                continue
            add(k, find_model(d), find_cfg(d), base_label + suf)
    return out


def detect_engine(cfg):
    """探测可用的 katago.exe / 权重 / 配置:
    先看 config 里的路径,再在常见位置搜。
    返回 {"katago":..., "model":..., "config":..., "found":bool, "notes":[...]}
    """
    eng = cfg.get("engine", {})
    root = base_dir()
    notes = []

    def first_existing(cands, pred):
        for c in cands:
            if c and os.path.exists(c) and pred(c):
                return c
        return None

    kcands = [eng.get("katago"),
              os.path.join(root, "KataGo-opencl", "katago.exe"),
              os.path.join(root, "engines", "KataGo-opencl", "katago.exe"),
              os.path.join(root, "KataGo-cpu", "katago.exe"),
              os.path.join(root, "engines", "KataGo-cpu", "katago.exe"),
              r"F:\围棋\KataGo-opencl\katago.exe",
              r"F:\围棋\KataGo-cpu\katago.exe",
              os.path.join(root, "katago.exe")]
    katago = first_existing(kcands, os.path.isfile)

    model, gcfg = None, None
    if katago:
        d = os.path.dirname(katago)
        md = [eng.get("model"),
              os.path.join(d, "kata1-tf3-b11c768-s11500M-d6163M.bin.gz")]
        try:
            md += [os.path.join(d, f) for f in sorted(os.listdir(d)) if f.endswith(".bin.gz")]
        except Exception:
            pass
        model = first_existing(md, os.path.isfile)

        cd = [eng.get("config"),
              os.path.join(d, "gtp_practice.cfg"),
              os.path.join(d, "gtp_play.cfg")]
        try:
            cd += [os.path.join(d, f) for f in sorted(os.listdir(d)) if f.endswith(".cfg")]
        except Exception:
            pass
        gcfg = first_existing(cd, os.path.isfile)

    if katago:
        notes.append("找到引擎: %s" % katago)
    else:
        notes.append("未找到 katago.exe —— 请在「设置」里指定路径")
    if katago and not model:
        notes.append("引擎目录下没找到 .bin.gz 权重")
    if katago and not gcfg:
        notes.append("引擎目录下没找到 .cfg 配置")
    return {"katago": katago, "model": model, "config": gcfg,
            "found": bool(katago and model and gcfg), "notes": notes}


def autofix_engine(cfg, save=True):
    """启动时兜底:配置里的路径若失效,自动探测可用引擎并写回 config.json。
    这样打包后的程序换台机器、或引擎目录改过名,也不至于直接开不了局。
    """
    eng = cfg.setdefault("engine", {})
    ok = all(eng.get(k) and os.path.exists(eng[k]) for k in ("katago", "model", "config"))
    if ok:
        return False, []
    d = detect_engine(cfg)
    if not d["found"]:
        return False, d["notes"]
    changed = False
    for k in ("katago", "model", "config"):
        if d.get(k) and not (eng.get(k) and os.path.exists(eng.get(k))):
            eng[k] = d[k]
            changed = True
    if changed and save:
        try:
            save_config(cfg)
        except Exception as e:
            log("autofix save failed: %s" % e)
    if changed:
        log("engine autofix -> %s" % eng.get("katago"))
    return changed, d["notes"]


# ---------------- 围棋规则 ----------------

class Board:
    def __init__(self, size):
        self.size = size
        self.g = [["." for _ in range(size)] for _ in range(size)]
        self.history = []          # 快照栈
        self.moves = []            # [(color, i, j)];pass 记 (-1, -1)
        self.captures = {"B": 0, "W": 0}
        self.ko = None             # 禁着点 (i,j)

    def clone_grid(self):
        return [row[:] for row in self.g]

    def push(self):
        self.history.append((self.clone_grid(), list(self.moves), dict(self.captures), self.ko))

    def pop(self):
        if not self.history:
            return False
        g, mv, cap, ko = self.history.pop()
        self.g, self.moves, self.captures, self.ko = g, mv, cap, ko
        return True

    def neighbors(self, i, j):
        n = self.size
        for di, dj in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            a, b = i + di, j + dj
            if 0 <= a < n and 0 <= b < n:
                yield a, b

    def group(self, i, j):
        color = self.g[i][j]
        seen, stack, libs = {(i, j)}, [(i, j)], set()
        while stack:
            x, y = stack.pop()
            for a, b in self.neighbors(x, y):
                v = self.g[a][b]
                if v == ".":
                    libs.add((a, b))
                elif v == color and (a, b) not in seen:
                    seen.add((a, b))
                    stack.append((a, b))
        return seen, libs

    def try_play(self, color, i, j):
        """返回 (ok, 提子列表, 错误信息)"""
        if self.g[i][j] != ".":
            return False, [], "该点已有子"
        if self.ko == (i, j):
            return False, [], "打劫禁着点(需先找劫材)"
        g = self.g
        g[i][j] = color
        opp = "W" if color == "B" else "B"
        captured = []
        for a, b in self.neighbors(i, j):
            if g[a][b] == opp:
                grp, libs = self.group(a, b)
                if not libs:
                    for (x, y) in grp:
                        g[x][y] = "."
                        captured.append((x, y))
        grp, libs = self.group(i, j)
        if not libs:
            g[i][j] = "."
            for (x, y) in captured:
                g[x][y] = opp
            return False, [], "自杀手(自己没气)"
        # 标准打劫:禁止全局同形再现(与引擎一致)
        if len(self.history) >= 2:
            prev = self.history[-2][0]        # 对方上一手之前的局面
            if all(g[x][y] == prev[x][y] for x in range(self.size) for y in range(self.size)):
                g[i][j] = "."
                for (x, y) in captured:
                    g[x][y] = opp
                return False, [], "打劫禁着点(需先找劫材)"
        self.ko = None
        return True, captured, ""

    def coord(self, i, j):
        return COLS[i] + str(self.size - j)

    def to_sgf(self, komi=7.5, handicap=0):
        s = ["(;GM[1]FF[4]CA[UTF-8]AP[GoDojo:web]SZ[%d]KM[%.1f]" % (self.size, komi)]
        if handicap:
            s.append("HA[%d]" % handicap)
        s.append("DT[%s]" % datetime.datetime.now().strftime("%Y-%m-%d"))
        for (c, i, j) in self.moves:
            if i < 0:
                s.append(";%s[]" % c)
            else:
                s.append(";%s[%s%s]" % (c, chr(97 + i), chr(97 + j)))
        s.append(")")
        return "".join(s)


# ---------------- 引擎 ----------------

# 各候选的探测超时(秒),按标签前缀匹配。
#   OpenCL(GPU): 新机器第一次跑要现场为显卡调优(编译内核),实测 5-10 分钟,
#                所以给足 15 分钟。调优结果会缓存到引擎目录,之后就秒起。
#   CPU:         没有调优环节,起不来就是真起不来,给 90 秒足够。
PROBE_TIMEOUT = {"OpenCL(GPU)": 900, "CPU": 90}
PROBE_TIMEOUT_DEFAULT = 240


def probe_timeout_for(label):
    """按候选标签取探测超时(标签可能带"(外部)"后缀,所以用前缀匹配)"""
    for k, v in PROBE_TIMEOUT.items():
        if label.startswith(k):
            return v
    return PROBE_TIMEOUT_DEFAULT


class Engine:
    """KataGo GTP 封装:串行调用,后台线程读输出

    启动时按候选列表逐个尝试(配置指定 -> OpenCL 版 -> CPU 版),
    某个引擎起来后立刻退出(回来后才算成功)。这样没有 OpenCL 显卡的
    机器会自动降级到 CPU 版,不会"装完打不开"。

    首次在新机器上跑 OpenCL 版时,KataGo 要先给显卡做调优(5-10 分钟,
    只在第一次),期间不会应答 GTP 命令。所以:
      - 探测超时按引擎类型给(见 PROBE_TIMEOUT)
      - 期间把进度写进 self.progress,界面据此提示"首次调优中",别让
        用户以为死机了
    """

    def __init__(self, cfg):
        self.cfg = cfg
        self.ok = False
        self.err = ""
        self.q = queue.Queue()
        self.lock = threading.Lock()
        self.op_lock = threading.RLock()      # 串行化整个引擎会话(写+读)
        self.p = None
        self.label = ""                       # 实际用上的引擎(GPU/CPU)
        self.notes = []                       # 各候选的失败原因(给人看的诊断)
        self.progress = ""                    # 启动阶段的进度说明(给界面显示)
        self._start()

    def _spawn(self, katago, model, gcfg):
        """启动引擎进程。

        stderr 单独开管道收货:引擎的日志/报错都在 stderr,若丢进 DEVNULL
        就变成"起不来但不知道为什么";也用来判断进程是不是刚启动就死了。
        """
        return subprocess.Popen(
            [katago, "gtp", "-model", model, "-config", gcfg],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, text=True, encoding="utf-8",
            errors="replace", bufsize=1, creationflags=_NO_WINDOW,
            cwd=os.path.dirname(katago))

    def _collect_err(self, p, store, on_line=None):
        """把引擎 stderr 收进 store(只留最后 8 行,够定位问题)

        on_line 不为空时,每来一行都回调一次 —— 用来识别"正在调优"这类
        需要告诉用户的动态。
        """
        try:
            for line in p.stderr:
                s = line.rstrip()
                if s:
                    store.append(s)
                    del store[:-8]
                    if on_line:
                        try:
                            on_line(s)
                        except Exception:
                            pass
        except Exception:
            pass

    def _start(self):
        cands = engine_candidates(self.cfg)
        if not cands:
            self.err = "没找到可用的引擎(katago.exe / 权重 / 配置)"
            log("engine start failed: " + self.err)
            return
        errs = []
        for cd in cands:
            label = cd["label"]
            tmo = probe_timeout_for(label)
            self.progress = "正在启动引擎[%s]…" % label
            try:
                p = self._spawn(cd["katago"], cd["model"], cd["config"])
            except Exception as e:
                errs.append("%s: 启动失败 %s" % (label, e))
                continue
            # 先起读线程(它把输出喂进 q),再探测:引擎要在超时内应答
            q = queue.Queue()
            self.q = q
            elog = []
            t0 = time.time()

            def on_err_line(s, _label=label, _t0=t0):
                """从引擎 stderr 里认调优迹象,实时更新进度提示"""
                low = s.lower()
                if "tuning" in low or ("opencl" in low and "found" in low):
                    self.progress = ("正在为显卡做首次调优(约 5-10 分钟,仅首次)…"
                                     "已等待 %d 秒" % int(time.time() - _t0))
                elif "loaded" in low and "model" in low:
                    self.progress = "%s: 正在加载神经网络…" % _label

            threading.Thread(target=self._reader, args=(p, q), daemon=True).start()
            threading.Thread(target=self._collect_err, args=(p, elog, on_err_line),
                             daemon=True).start()

            # 探测期间给个计时线程,让界面能看到"还在等,不是死了"
            stop_tick = threading.Event()

            def ticker(_label=label, _t0=t0):
                while not stop_tick.wait(5):
                    el = time.time() - _t0
                    if el > 25 and "调优" not in self.progress:
                        self.progress = "%s: 启动中… 已等待 %d 秒" % (_label, int(el))

            threading.Thread(target=ticker, daemon=True).start()
            good = self._probe(p, q, timeout=tmo)
            stop_tick.set()

            if good:
                self.p = p
                self.ok = True
                self.label = label
                self.progress = ""
                self._drain(timeout=0.2)      # 清掉探测残留的空行,免得污染后续读响应
                log("engine started [%s]: %s" % (label, cd["katago"]))
                return
            # 起不来 -> 收尸后试下一个
            rc = p.poll()
            try:
                p.kill()
                p.wait(timeout=5)
            except Exception:
                pass
            why = ("进程已退出 rc=%s" % rc) if rc is not None else "无响应(超过 %ds)" % tmo
            tail = "; ".join(elog[-3:]) if elog else ""
            errs.append("%s: %s%s" % (label, why, (" | " + tail) if tail else ""))
        self.err = "; ".join(errs) or "引擎启动失败"
        self.notes = list(errs)
        self.progress = ""
        log("engine start failed: %s" % self.err)

    def _reader(self, p=None, q=None):
        """把进程输出持续喂进队列(默认当前引擎 + self.q)

        起引擎时会逐个候选尝试,q 显式传入:上一轮候选的读线程若还活着,
        也只会继续往它自己的旧队列里塞,不会污染新一轮的 self.q。
        """
        try:
            for line in (p or self.p).stdout:
                (q or self.q).put(line)
        except Exception:
            pass

    def _probe(self, p, q=None, timeout=40):
        """发两条 setup 命令,确认引擎真的能应答(读线程已在跑,这里带超时等)

        探测期间引擎还没"上岗"(self.p 仍为 None),所以写命令和读队列
        都要显式指定目标进程/队列。

        进程一旦退出就立刻返回 False:引擎崩了(缺 DLL / 显卡不支持)时
        没必要把 40 秒等满,用户也不会盯着"启动中"发呆。
        """
        q = q or self.q
        try:
            self.write("boardsize 9", p=p)
            self.write("clear_board", p=p)
        except Exception:
            return False
        t0, seen = time.time(), 0
        while time.time() - t0 < timeout:
            if p.poll() is not None:          # 进程已死,再等也没用
                return False
            try:
                line = q.get(timeout=0.3)
            except queue.Empty:
                continue
            if line.lstrip().startswith(("=", "?")):
                seen += 1
                if seen >= 2:
                    return True
        return False

    def shutdown(self, wait=1.5):
        """优雅退出:拿不到锁(正在 genmove)就直接 kill,绝不多等"""
        try:
            if not (self.p and self.p.poll() is None):
                return
            if self.op_lock.acquire(blocking=False):
                try:
                    self.p.stdin.write("quit\n")
                    self.p.stdin.flush()
                except Exception:
                    pass
                finally:
                    self.op_lock.release()
            try:
                self.p.wait(timeout=wait)
            except Exception:
                pass
            if self.p.poll() is None:
                self.p.kill()
                try:
                    self.p.wait(timeout=3)
                except Exception:
                    pass
            log("engine subprocess exited (rc=%s)" % self.p.poll())
        except Exception as e:
            log("shutdown err: %s" % e)

    def restart(self):
        """引擎崩溃/退出后重启(网络版的自愈能力)"""
        self.shutdown()
        self.p = None                 # 旧进程已收尸,别让 alive() 误判
        self.q = queue.Queue()
        self.ok = False
        self.label = ""
        self.err = ""
        self._start()
        return self.ok

    def alive(self):
        return bool(self.p) and self.p.poll() is None

    def write(self, cmd, p=None):
        """p 不传时写当前引擎;起引擎探测阶段要显式传候选进程"""
        with self.lock:
            (p or self.p).stdin.write(cmd + "\n")
            (p or self.p).stdin.flush()

    def op_begin(self):
        """串行化所有引擎交互(评估线程与对局线程会抢管道)"""
        self.op_lock.acquire()

    def op_end(self):
        try:
            self.op_lock.release()
        except Exception:
            pass

    def _drain(self, timeout=0.1):
        out = []
        while True:
            try:
                out.append(self.q.get(timeout=timeout))
            except queue.Empty:
                return out

    def read_response(self, timeout=120):
        lines, t0 = [], time.time()
        while time.time() - t0 < timeout:
            try:
                line = self.q.get(timeout=0.2)
            except queue.Empty:
                continue
            s = line.rstrip("\r\n")
            if s == "":
                break
            lines.append(s)
        return lines

    def cmd(self, c, timeout=120):
        with self.op_lock:
            self.write(c)
            return self.read_response(timeout)

    def cmd_first_value(self, c, timeout=120):
        lines = self.cmd(c, timeout)
        for ln in lines:
            if ln.startswith("=") or ln.startswith("?"):
                v = ln[1:].strip()
                return v
        return ""

    def setup(self, size, komi=7.5):
        self.cmd("boardsize %d" % size)
        self.cmd("clear_board")
        self.cmd("komi %s" % komi)

    def play(self, color, coord):
        """返回 True 表示引擎接受;False 表示引擎判非法(盘面可能脱节)"""
        lines = self.cmd("play %s %s" % (color, coord), timeout=15)
        for ln in lines:
            if ln.startswith("?"):
                log("engine rejected play %s %s -> %s" % (color, coord, ln))
                return False
        return True

    def resync(self, moves):
        """用应用的着法历史重建引擎盘面"""
        try:
            self.cmd("clear_board")
            for (c, coord) in moves:
                self.cmd("play %s %s" % (c, coord))
            log("resync done, %d moves" % len(moves))
        except Exception as e:
            log("resync failed: %s" % e)

    def undo(self):
        self.cmd("undo")

    def set_visits(self, n):
        """动态调整引擎强度(每手思考量)"""
        try:
            self.cmd("kata-set-param maxVisits %d" % int(n))
            log("maxVisits -> %d" % int(n))
        except Exception as e:
            log("set_visits failed: %s" % e)

    def genmove_analyze(self, color, maxmoves=5, interval=100):
        """返回 (move, info_dict)
        注意:引擎会先回一个裸 '=' (命令已接受),之后才是 info 流和 play XXX
        """
        self.op_begin()
        self.write("kata-genmove_analyze %s interval %d maxmoves %d" % (color, interval, maxmoves))
        infos, move = [], ""
        t0 = time.time()
        while time.time() - t0 < 180:
            try:
                line = self.q.get(timeout=0.2)
            except queue.Empty:
                continue
            s = line.rstrip("\r\n")
            if s.startswith("info "):
                infos.append(s.strip())
                continue
            if s.startswith("play "):
                move = s.split()[1]
                continue
            if s.startswith("=") or s.startswith("?"):
                v = s[1:].strip()
                if v and not move:
                    move = v
                if move:
                    break
                continue                      # 裸 "=" :继续等分析流
            if s.strip() == "":
                if move:
                    break
                continue
        self.op_end()
        return move, parse_info(infos)

    def analyze(self, color, secs=1.6, maxmoves=5):
        """纯分析(不改局面)"""
        self.op_begin()
        self.write("kata-analyze %s interval 100 maxmoves %d" % (color, maxmoves))
        infos, t0 = [], time.time()
        while time.time() - t0 < secs:
            try:
                line = self.q.get(timeout=0.1)
            except queue.Empty:
                continue
            s = line.strip()
            if s.startswith("info "):
                infos.append(s)
        self.write("protocol_version")        # 打断分析
        t1 = time.time()
        while time.time() - t1 < 3:
            try:
                s = self.q.get(timeout=0.1).strip()
            except queue.Empty:
                continue
            if s == "" or s.startswith("=") or s.startswith("?"):
                break
        self._drain(0.05)
        self.op_end()
        return parse_info(infos)
