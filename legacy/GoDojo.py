# -*- coding: utf-8 -*-
"""GoDojo — 简易交互式围棋(AI 陪练 + 实时讲评)
- 你点棋盘落子;AI 自动应手(KataGo 引擎)
- 实时显示:胜率条、目差、AI 推荐点、你上一手的得失
- 自动记谱(SGF),支持悔棋 / 提示 / 停一手 / 换棋盘大小 / 换先后手
依赖:Python3 + tkinter + D:\\Go\\KataGo-opencl\\katago.exe
"""
import os, sys, time, json, queue, threading, datetime, subprocess, traceback, ctypes, re

# 让界面按原生分辨率渲染(否则高分屏下会被放大、超出屏幕)
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)      # per-monitor DPI aware
except Exception:
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass

import tkinter as tk
from tkinter import messagebox, filedialog

# ---------------- 引擎 ----------------
BASE   = r"F:\围棋"
KATAGO = r"F:\围棋\KataGo-opencl\katago.exe"
NET    = r"F:\围棋\KataGo-opencl\kata1-tf3-b11c768-s11500M-d6163M.bin.gz"
CFG    = r"F:\围棋\KataGo-opencl\gtp_practice.cfg"
GAMES  = r"F:\围棋\games"
EXT_DIR = r"F:\围棋\外接AI"
LOG    = r"F:\围棋\godojo.log"


LETTERS = "ABCDEFGHJKLMNOPQRST"
COLS = "ABCDEFGHJKLMNOPQRST"


def log(msg):
    try:
        with open(LOG, "a", encoding="utf-8") as f:
            f.write("%s %s\n" % (datetime.datetime.now().strftime("%H:%M:%S"), msg))
    except Exception:
        pass


class Engine:
    """KataGo GTP 封装:串行调用,后台线程读输出"""

    def __init__(self):
        self.ok = False
        self.err = ""
        self.q = queue.Queue()
        self.lock = threading.Lock()
        self.op_lock = threading.RLock()      # 串行化整个引擎会话(写+读)
        try:
            self.p = subprocess.Popen(
                [KATAGO, "gtp", "-model", NET, "-config", CFG],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL, text=True, encoding="utf-8",
                errors="replace", bufsize=1)
            threading.Thread(target=self._reader, daemon=True).start()
            self.ok = True
        except Exception as e:
            self.err = str(e)
            log("engine start failed: %s" % e)

    def _reader(self):
        try:
            for line in self.p.stdout:
                self.q.put(line)
        except Exception:
            pass

    def write(self, cmd):
        with self.lock:
            self.p.stdin.write(cmd + "\n")
            self.p.stdin.flush()

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
        lines = self.cmd("play %s %s" % (color, coord))
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


def disp_wr(lead, size):
    """用目差换算"展示用胜率":9 路 1 目价值大,19 路 1 目价值小"""
    if lead is None:
        return None
    import math
    scale = 1.2 if size <= 9 else (2.5 if size <= 13 else 6.0)
    return 1.0 / (1.0 + math.exp(-lead / scale))


def handicap_points(size, n):
    """返回让 n 子的坐标列表 [(i, j)]（j=0 为最上一行）"""
    if size == 9:
        hoshi = [(2, 2), (6, 6)]          # C7, G3(对角)
        center = (4, 4)                    # E5
        corners = [(2, 2), (6, 6), (2, 6), (6, 2)]   # C7 G3 C3 G7
    else:
        hoshi = [(15, 3), (3, 15)]         # Q16, D4
        center = (9, 9)                    # K10
        corners = [(15, 3), (3, 15), (3, 3), (15, 15)]
    if n <= 2:
        return hoshi[:n]
    if n == 3:
        return hoshi + [center]
    if n == 4:
        return corners
    return corners + [center]


def parse_info(infos):
    if not infos:
        return None
    import re

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


# ---------------- 围棋规则 ----------------
class Board:
    def __init__(self, size):
        self.size = size
        self.g = [["." for _ in range(size)] for _ in range(size)]
        self.history = []          # 快照栈
        self.moves = []            # [(color, i, j)]
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

    def to_sgf(self, komi=7.5):
        s = ["(;GM[1]FF[4]CA[UTF-8]SZ[%d]KM[%.1f]DT[%s]" % (self.size, komi,
             datetime.datetime.now().strftime("%Y-%m-%d"))]
        for (c, i, j) in self.moves:
            s.append(";%s[%s%s]" % (c, chr(97 + i), chr(97 + j)))
        s.append(")")
        return "".join(s)


# ---------------- 界面 ----------------
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("GoDojo · 围棋陪练(DSH)")
        self.geometry("1240x860+40+20")
        self.minsize(980, 700)
        self.configure(bg="#20242b")

        self.size = 9
        self.human = "B"
        self.komi = 7.5
        self.board = Board(self.size)
        self.busy = False
        self.last_move = None
        self.ai_eval = None
        self.human_last_eval = None       # 你上一手的评价
        self.pending_before = None        # 你走之前的胜率(用于评价)
        self.sgf_path = None
        self.engine = None
        self.opponent = "ai"              # "ai"=内置KataGo, "external"=外接AI(文件接口)

        self._build_ui()
        self.after(400, self._dbg_win)
        self.after(200, self._boot_engine)
        if "--ai-vs-ai" in sys.argv:          # 命令行直接进入 AI 对 AI 模式
            self.opp_var.set("AI对AI(双文件)")
            self.after(1200, self.new_game)
        # 命令行参数:--handicap N  --visits N  --new
        try:
            if "--size" in sys.argv:
                self.size_var.set(str(int(sys.argv[sys.argv.index("--size") + 1])))
            if "--handicap" in sys.argv:
                self.handicap_var.set("%d 子" % int(sys.argv[sys.argv.index("--handicap") + 1]))
            if "--visits" in sys.argv:
                self.level_var.set(int(sys.argv[sys.argv.index("--visits") + 1]))
        except Exception as e:
            log("cli args err %s" % e)
        if "--new" in sys.argv:
            self.after(2500, self.new_game)

    def _dbg_win(self):
        try:
            log("win mapped=%s viewable=%s state=%s geom=%s screen=%sx%s" % (
                self.winfo_ismapped(), self.winfo_viewable(), self.state(),
                self.geometry(), self.winfo_screenwidth(), self.winfo_screenheight()))
            self.deiconify(); self.lift(); self.attributes("-topmost", True)
            self.after(1500, lambda: self.attributes("-topmost", False))
        except Exception as e:
            log("dbg err %s" % e)

    # ---- UI ----
    def _build_ui(self):
        top = tk.Frame(self, bg="#2b313a")
        top.pack(side="top", fill="x")
        tk.Label(top, text="GoDojo", bg="#2b313a", fg="#7fd1a6",
                 font=("Microsoft YaHei", 14, "bold")).pack(side="left", padx=10, pady=6)

        self.size_var = tk.StringVar(value="9")
        tk.Label(top, text="棋盘", bg="#2b313a", fg="#ddd").pack(side="left", padx=(16, 2))
        tk.OptionMenu(top, self.size_var, "9", "13", "19", command=lambda *_: self.new_game()).pack(side="left")

        self.color_var = tk.StringVar(value="黑(先手)")
        tk.Label(top, text="你执", bg="#2b313a", fg="#ddd").pack(side="left", padx=(16, 2))
        tk.OptionMenu(top, self.color_var, "黑(先手)", "白(后手)", command=lambda *_: self.new_game()).pack(side="left")

        self.opp_var = tk.StringVar(value="内置AI")
        tk.Label(top, text="对手", bg="#2b313a", fg="#ddd").pack(side="left", padx=(16, 2))
        tk.OptionMenu(top, self.opp_var, "内置AI", "外接AI(文件)", "AI对AI(双文件)",
                      command=lambda *_: self.new_game()).pack(side="left")

        self.handicap_var = tk.StringVar(value="0 (分先)")
        tk.Label(top, text="让子", bg="#2b313a", fg="#ddd").pack(side="left", padx=(16, 2))
        tk.OptionMenu(top, self.handicap_var, "0 (分先)", "2 子", "3 子", "4 子", "5 子",
                      command=lambda *_: self.new_game()).pack(side="left")

        self.level_var = tk.IntVar(value=120)
        tk.Label(top, text="AI强度(visits)", bg="#2b313a", fg="#ddd").pack(side="left", padx=(16, 2))
        tk.Scale(top, from_=20, to=800, orient="horizontal", variable=self.level_var,
                 bg="#2b313a", fg="#ddd", highlightthickness=0, length=180).pack(side="left")

        btns = tk.Frame(self, bg="#2b313a")
        btns.pack(side="top", fill="x")
        for text, cb in (("新局", self.new_game), ("悔棋", self.undo), ("提示", self.hint),
                         ("停一手", self.pass_move), ("认输", self.resign),
                         ("分析", self.analyse_now), ("保存棋谱", self.save_sgf)):
            tk.Button(btns, text=text, command=cb, width=9,
                      bg="#39414d", fg="#eee", activebackground="#4a5563",
                      relief="flat").pack(side="left", padx=4, pady=6)

        main = tk.Frame(self, bg="#20242b")
        main.pack(side="top", fill="both", expand=True)

        self.canvas = tk.Canvas(main, bg="#e9cb8f", highlightthickness=0)
        self.canvas.pack(side="left", fill="both", expand=True, padx=10, pady=10)
        self.canvas.bind("<Button-1>", self.on_click)
        self.canvas.bind("<Motion>", self.on_motion)
        self.canvas.bind("<Configure>", lambda e: self.redraw())

        side = tk.Frame(main, bg="#20242b", width=330)
        side.pack(side="right", fill="y", padx=(0, 10), pady=10)
        side.pack_propagate(False)

        self.status = tk.StringVar(value="引擎启动中…")
        tk.Label(side, textvariable=self.status, bg="#20242b", fg="#ffd54f",
                 font=("Microsoft YaHei", 10), wraplength=320, justify="left").pack(anchor="w")

        self.evalbar = tk.Canvas(side, height=26, bg="#2b313a", highlightthickness=0)
        self.evalbar.pack(fill="x", pady=(10, 2))
        self.evaltext = tk.StringVar(value="胜率: --")
        tk.Label(side, textvariable=self.evaltext, bg="#20242b", fg="#eee",
                 font=("Consolas", 11)).pack(anchor="w")

        self.candbox = tk.Text(side, height=7, bg="#161a20", fg="#9fd3a5",
                               font=("Consolas", 10), relief="flat")
        self.candbox.pack(fill="x", pady=(8, 8))

        tk.Label(side, text="对局记录", bg="#20242b", fg="#8fa6bd",
                 font=("Microsoft YaHei", 10)).pack(anchor="w")
        self.movelist = tk.Text(side, bg="#161a20", fg="#dbe6f0",
                                font=("Consolas", 10), relief="flat")
        self.movelist.pack(fill="both", expand=True)

        self.coach = tk.StringVar(value="")
        tk.Label(side, textvariable=self.coach, bg="#20242b", fg="#ffab91",
                 font=("Microsoft YaHei", 10), wraplength=320, justify="left").pack(anchor="w", pady=(8, 0))

    # ---- 引擎启动 ----
    def _boot_engine(self):
        def work():
            self.engine = Engine()
            if self.engine.ok:
                self.engine.setup(self.size, self.komi)
                self.set_status("引擎就绪 ✅  点棋盘落子(你执%s)" % ("黑" if self.human == "B" else "白"))
            else:
                self.set_status("引擎启动失败: %s" % self.engine.err)
        threading.Thread(target=work, daemon=True).start()

    def set_status(self, s):
        self.after(0, lambda: self.status.set(s))

    def set_coach(self, s):
        self.after(0, lambda: self.coach.set(s))

    # ---- 绘制 ----
    def geom(self):
        w = self.canvas.winfo_width() or 600
        h = self.canvas.winfo_height() or 600
        pad = 46
        cell = max(14, min((w - 2 * pad) / (self.size - 1), (h - 2 * pad) / (self.size - 1)))
        ox = (w - cell * (self.size - 1)) / 2
        oy = (h - cell * (self.size - 1)) / 2
        return cell, ox, oy

    def redraw(self):
        c = self.canvas
        c.delete("all")
        cell, ox, oy = self.geom()
        n = self.size
        for k in range(n):
            c.create_line(ox, oy + k * cell, ox + (n - 1) * cell, oy + k * cell, fill="#6b4a24")
            c.create_line(ox + k * cell, oy, ox + k * cell, oy + (n - 1) * cell, fill="#6b4a24")
        stars = {9: [(2, 2), (6, 2), (4, 4), (2, 6), (6, 6)],
                 13: [(3, 3), (9, 3), (6, 6), (3, 9), (9, 9)],
                 19: [(3, 3), (9, 3), (15, 3), (3, 9), (9, 9), (15, 9), (3, 15), (9, 15), (15, 15)]}.get(n, [])
        for (i, j) in stars:
            x, y = ox + i * cell, oy + j * cell
            c.create_oval(x - 3, y - 3, x + 3, y + 3, fill="#6b4a24", outline="")
        for i in range(n):
            c.create_text(ox + i * cell, oy + (n - 1) * cell + 24, text=COLS[i],
                          fill="#6b4a24", font=("Consolas", 10))
        for j in range(n):
            c.create_text(ox - 24, oy + j * cell, text=str(n - j),
                          fill="#6b4a24", font=("Consolas", 10))
        r = cell * 0.46
        for i in range(n):
            for j in range(n):
                v = self.board.g[i][j]
                if v == ".":
                    continue
                x, y = ox + i * cell, oy + j * cell
                fill = "#111111" if v == "B" else "#fbfbfb"
                outline = "#000" if v == "B" else "#9a9a9a"
                c.create_oval(x - r, y - r, x + r, y + r, fill=fill, outline=outline, width=1.4)
        if self.last_move:
            i, j = self.last_move
            x, y = ox + i * cell, oy + j * cell
            c.create_oval(x - 4, y - 4, x + 4, y + 4, fill="#e53935", outline="")
        # 推荐点
        if getattr(self, "hint_pts", None):
            for lm, (i, j) in zip("ABCDE", self.hint_pts):
                x, y = ox + i * cell, oy + j * cell
                c.create_oval(x - r, y - r, x + r, y + r, outline="#1b7f3a", width=2, dash=(3, 2))
                c.create_text(x, y, text=lm, fill="#1b7f3a", font=("Microsoft YaHei", 11, "bold"))

    def on_motion(self, ev):
        if self.busy:
            return
        cell, ox, oy = self.geom()
        i = round((ev.x - ox) / cell)
        j = round((ev.y - oy) / cell)
        n = self.size
        if 0 <= i < n and 0 <= j < n and abs(ev.x - (ox + i * cell)) < cell * .5 and abs(ev.y - (oy + j * cell)) < cell * .5:
            self.canvas.configure(cursor="hand2")
        else:
            self.canvas.configure(cursor="")

    # ---- 落子 ----
    def on_click(self, ev):
        if self.busy or not self.engine or not self.engine.ok:
            return
        cell, ox, oy = self.geom()
        i = round((ev.x - ox) / cell)
        j = round((ev.y - oy) / cell)
        n = self.size
        if not (0 <= i < n and 0 <= j < n):
            return
        if abs(ev.x - (ox + i * cell)) > cell * .5 or abs(ev.y - (oy + j * cell)) > cell * .5:
            return
        if self.board.g[i][j] != ".":
            return
        # 轮到你?(让子局白方先行,用 side_to_move 判断)
        if self.side_to_move() != self.human:
            self.set_status("现在不是你的回合")
            return
        self.human_play(i, j)

    def side_to_move(self):
        """当前该谁走(考虑让子:让子局白先行)"""
        if not self.board.moves:
            return "W" if self.handicap > 0 else "B"
        return "W" if self.board.moves[-1][0] == "B" else "B"

    def human_play(self, i, j):
        before = self.human_last_eval if False else (self.ai_eval or {}).get("human_wr")
        self.board.push()
        ok, cap, err = self.board.try_play(self.human, i, j)
        if not ok:
            self.board.pop()
            self.set_status("❌ " + err)
            return
        self.board.moves.append((self.human, i, j))
        self.board.captures[self.human] += len(cap)
        self.last_move = (i, j)
        self.hint_pts = None
        self.redraw()
        self.refresh_movelist()
        self.save_sgf(silent=True)
        coord = self.board.coord(i, j)
        self.set_status("你下 %s%s" % (coord, "(提%d子)" % len(cap) if cap else ""))
        self.busy = True
        threading.Thread(target=self._after_human, args=(coord,), daemon=True).start()

    def _after_human(self, coord):
        try:
            e = self.engine
            if not e.play(self.human, coord):
                # 引擎判非法(通常是打劫) -> 撤销这一手,提示玩家重下
                e.resync([(c, self.board.coord(i, j))
                          for (c, i, j) in self.board.moves if i >= 0][:-1])
                self.after(0, self._revert_last)
                return
            # 1) 分析当前局面(AI 视角),用于讲评你的上一手
            info_ai = e.analyze(self.ai_color(), secs=1.2, maxmoves=5)
            lead_ai_a = info_ai.get("scoreLead") if info_ai else None
            human_wr = disp_wr(-lead_ai_a, self.size) if lead_ai_a is not None else None
            prev = self.pending_before
            if human_wr is not None and prev is not None:
                delta = (human_wr - prev) * 100
                best = ", ".join(c["move"] for c in (info_ai or {}).get("cands", [])[:3])
                if delta < -12:
                    msg = "⚠️ 你这手掉了 %.0f%% 胜率;引擎推荐:%s" % (-delta, best)
                elif delta < -4:
                    msg = "🙂 这手稍缓(%.0f%%),推荐:%s" % (delta, best)
                else:
                    msg = "✅ 好手!胜率 %.0f%%(推荐点:%s)" % (human_wr * 100, best)
                self.set_coach(msg)
            # 2) 对手应手:外接AI 走文件接口,内置AI 走引擎
            if self.opponent == "external":
                self.ext_turn()
                return
            mv, info = e.genmove_analyze(self.ai_color(), maxmoves=5, interval=100)
            if not mv or mv.lower() in ("pass", "resign"):
                self.after(0, lambda m=mv: self.set_status("AI:%s" % m))
                self.busy = False
                return
            i = COLS.index(mv[0].upper())
            j = self.size - int(mv[1:])
            cap = []
            if self.board.g[i][j] == ".":
                ok, cap, err = self.board.try_play(self.ai_color(), i, j)
                if not ok:
                    log("AI illegal %s: %s" % (mv, err))
                    self.set_status("AI 落子异常(%s),已跳过" % err)
                    self.busy = False
                    return
            self.board.moves.append((self.ai_color(), i, j))
            self.board.captures[self.ai_color()] += len(cap)
            self.last_move = (i, j)
            # AI 视角 -> 人类视角(胜率用目差换算,引擎 9 路胜率头未校准)
            lead_ai = (info or {}).get("scoreLead")
            lead_human = (-lead_ai) if lead_ai is not None else None
            human_wr2 = disp_wr(lead_human, self.size) if lead_human is not None else None
            self.pending_before = human_wr2
            self.after(0, lambda: self._after_ai(mv, human_wr2, lead_human, info))
        except Exception as ex:
            log("after_human error: %s\n%s" % (ex, traceback.format_exc()))
            self.set_status("出错: %s" % ex)
            self.busy = False

    def _after_ai(self, mv, human_wr, lead, info):
        self.busy = False
        self.ai_eval = {"human_wr": human_wr, "lead": lead, "info": info}
        self.redraw()
        self.refresh_movelist()
        self.save_sgf(silent=True)
        self.update_eval(human_wr, lead, info)
        self.set_status("AI 下 %s ✅  轮到你" % mv)

    def update_eval(self, human_wr, lead, info):
        c = self.evalbar
        c.delete("all")
        w = c.winfo_width() or 320
        if human_wr is not None:
            c.create_rectangle(0, 0, w, 26, fill="#f4f4f4", outline="")
            c.create_rectangle(0, 0, w * human_wr, 26, fill="#222", outline="")
            c.create_text(w / 2, 13, text="你 %.0f%%" % (human_wr * 100),
                          fill="#e53935" if human_wr < .5 else "#1b7f3a",
                          font=("Microsoft YaHei", 10, "bold"))
        txt = "估算胜率: %s   目差: %s" % (
            ("%.1f%%" % (human_wr * 100)) if human_wr is not None else "--",
            ("%+.1f" % lead) if lead is not None else "--")
        self.evaltext.set(txt)
        if info and info.get("cands"):
            rows = ["AI 候选点(目差为你方视角):"]
            for cd in info["cands"][:5]:
                sl = cd["scoreLead"]
                rows.append("  %-4s  目差 %s" % (
                    cd["move"],
                    ("%+.1f" % (-sl)) if sl is not None else "--"))
            self.candbox.delete("1.0", "end")
            self.candbox.insert("end", "\n".join(rows))

    def ai_color(self):
        return "W" if self.human == "B" else "B"

    # ---- 操作 ----
    def new_game(self):
        self.size = int(self.size_var.get())
        self.human = "B" if self.color_var.get().startswith("黑") else "W"
        opt = self.opp_var.get()
        self.opponent = "both" if opt.startswith("AI对AI") else ("external" if opt.startswith("外接") else "ai")
        # 让子:人类(黑)先摆 N 子,白方(AI)先行;让子局贴目 0.5
        hc = self.handicap_var.get()
        self.handicap = int(hc.split()[0]) if hc.split()[0].isdigit() else 0
        self.komi = 0.5 if self.handicap > 0 else 7.5
        self.board = Board(self.size)
        self.last_move = None
        self.ai_eval = None
        self.pending_before = None
        self.hint_pts = None
        self.busy = False
        self.sgf_path = None          # 新局 -> 换新棋谱文件(避免覆盖上一盘)
        self.movelist.delete("1.0", "end")
        self.candbox.delete("1.0", "end")
        self.coach.set("")
        # 摆让子
        if self.handicap > 0:
            for (i, j) in handicap_points(self.size, self.handicap):
                ok, cap, err = self.board.try_play("B", i, j)
                if ok:
                    self.board.moves.append(("B", i, j))
                    self.last_move = (i, j)
            log("handicap %d placed, komi %.1f" % (self.handicap, self.komi))
        self.redraw()
        self.save_sgf(silent=True)
        if self.opponent in ("external", "both"):
            for f in ("ai_move.txt", "ai_error.txt", "black_move.txt", "white_move.txt"):
                try:
                    os.remove(os.path.join(EXT_DIR, f))
                except Exception:
                    pass
            self.write_ext_position()
        if self.opponent == "both":
            self.set_status("🤖 AI对AI 模式:黑棋写 black_move.txt,白棋写 white_move.txt")
            def work_both():
                if self.engine and self.engine.ok:
                    self.engine.setup(self.size, self.komi)   # 必须初始化,否则评估用错棋盘
                    log("ai-vs-ai engine setup: %d路 komi %.1f" % (self.size, self.komi))
                self.ai_vs_ai()
            threading.Thread(target=work_both, daemon=True).start()
            return
        if self.engine and self.engine.ok:
            def work():
                self.engine.setup(self.size, self.komi)
                self.engine.set_visits(self.level_var.get())    # 强度滑块真正生效
                if self.handicap > 0:                     # 让子:把预先摆好的黑子喂给引擎
                    for (i, j) in handicap_points(self.size, self.handicap):
                        self.engine.play("B", self.board.coord(i, j))
                if self.human == "W" or self.handicap > 0:   # 让子局由白方(AI)先行
                    if self.opponent == "external":
                        self.ext_turn()
                    else:
                        self.ai_first_move()
                else:
                    self.set_status("新局开始:你执黑先下" +
                                    ("(对手=外接AI,轮到它时请读 %s)" % EXT_DIR
                                     if self.opponent == "external" else ""))
            threading.Thread(target=work, daemon=True).start()

    # ---------- 外接 AI(文件接口)----------
    def write_ext_position(self):
        """把当前局面写成文本,供外部 AI 读取"""
        os.makedirs(EXT_DIR, exist_ok=True)
        L = []
        L.append("=== 围棋对局 · 外接AI 接口 ===")
        L.append("棋盘: %d 路   贴目: %.1f   当前第 %d 手" % (self.size, self.komi, len(self.board.moves)))
        if self.opponent == "both":
            nxt0 = "黑" if len(self.board.moves) % 2 == 0 else "白"
            L.append("对局双方: 黑 = DeepSeek(本机)   白 = 外部AI(GPT)")
            L.append("现在轮到: %s" % nxt0)
        else:
            L.append("你(外接AI)执: %s     对手(GoDojo内置KataGo)执: %s" %
                     ("黑" if self.ai_color() == "B" else "白",
                      "黑" if self.human == "B" else "白"))
        L.append("")
        L.append("局面(行号从下往上 1..%d,列 A..%s;大写=黑子,小写=白子,. = 空点):" % (
            self.size, "ABCDEFGHJKLMNOPQRST"[self.size - 1]))
        L.append("      " + " ".join("ABCDEFGHJKLMNOPQRST"[i] for i in range(self.size)))
        for j in range(self.size):
            row = []
            for i in range(self.size):
                v = self.board.g[i][j]
                row.append("." if v == "." else ("X" if v == "B" else "O"))
            L.append("%4d  %s" % (self.size - j, " ".join(row)))
        L.append("")
        L.append("着法历史: " + ",".join(
            ("B" if c == "B" else "W") + self.board.coord(i, j)
            for (c, i, j) in self.board.moves if i >= 0))
        L.append("")
        # 空点列表(合法落点候选,已排除已有子)
        empt = [self.board.coord(i, j) for j in range(self.size) for i in range(self.size)
                if self.board.g[i][j] == "."]
        L.append("空点(%d 个): %s" % (len(empt), " ".join(empt)))
        L.append("")
        if self.opponent == "both":
            nxt = "B" if len(self.board.moves) % 2 == 0 else "W"
            f = "black_move.txt" if nxt == "B" else "white_move.txt"
            L.append(">>> 现在轮到: %s" % ("黑" if nxt == "B" else "白"))
            L.append(">>> 请把着法写入: %s" % os.path.join(EXT_DIR, f))
            L.append(">>> 只写一个坐标(如 E5),停一手写 pass")
        else:
            L.append(">>> 请把你的下一手写入文件: %s" % os.path.join(EXT_DIR, "ai_move.txt"))
            L.append(">>> 只写一个坐标即可,例如: E5   (停一手写 pass)")
        with open(os.path.join(EXT_DIR, "position.txt"), "w", encoding="utf-8") as f:
            f.write("\n".join(L))
        log("external position written (%d moves)" % len(self.board.moves))

    def ext_turn(self):
        """轮到外接 AI:写局面 + 轮询它的着法"""
        self.busy = True
        self.write_ext_position()
        self.set_status("⏳ 轮到外接AI —— 请让它读 %s\\position.txt,并把着法写入 ai_move.txt" % EXT_DIR)
        mf = os.path.join(EXT_DIR, "ai_move.txt")
        ef = os.path.join(EXT_DIR, "ai_error.txt")
        try:
            if os.path.exists(ef):
                os.remove(ef)
        except Exception:
            pass
        mv = None
        for _ in range(3600):                 # 最多等 60 分钟
            if os.path.exists(mf):
                try:
                    txt = open(mf, encoding="utf-8-sig").read().strip()
                except Exception:
                    txt = ""
                if txt:
                    m = re.search(r"\b(pass|[A-Ta-t]\s*\d{1,2})\b", txt)
                    if m:
                        mv = m.group(1).replace(" ", "").upper()
                        try:
                            os.remove(mf)
                        except Exception:
                            pass
                        break
            time.sleep(1)
        if not mv:
            self.set_status("外接AI 超时未落子")
            self.busy = False
            return
        # 校验并落子
        if mv == "PASS":
            self.board.push()
            self.board.moves.append((self.ai_color(), -1, -1))
            self.after(0, self._ext_done_pass)
            return
        i = COLS.index(mv[0])
        j = self.size - int(mv[1:])
        self.board.push()
        ok, cap, err = self.board.try_play(self.ai_color(), i, j)
        if not ok:
            self.board.pop()
            with open(ef, "w", encoding="utf-8") as f:
                f.write("非法着法 %s: %s\n请重新把着法写入 ai_move.txt\n" % (mv, err))
            self.set_status("外接AI 的着法非法(%s),已写入 ai_error.txt,请重下" % err)
            self.busy = False
            threading.Thread(target=self.ext_turn, daemon=True).start()
            return
        self.board.moves.append((self.ai_color(), i, j))
        self.board.captures[self.ai_color()] += len(cap)
        self.last_move = (i, j)
        self.after(0, lambda: self._ext_done(mv, cap))

    def _ext_done(self, mv, cap):
        self.busy = False
        self.redraw()
        self.refresh_movelist()
        self.save_sgf(silent=True)
        self.write_ext_position()
        self.set_status("外接AI 下 %s%s ✅  轮到你" % (mv, "(提%d子)" % len(cap) if cap else ""))

    def _ext_done_pass(self):
        self.busy = False
        self.redraw()
        self.refresh_movelist()
        self.save_sgf(silent=True)
        self.write_ext_position()
        self.set_status("外接AI 停一手 —— 轮到你")

    # ---------- AI 对 AI(双方都走文件)----------
    def _wait_move(self, path, timeout=3600):
        for _ in range(timeout):
            if os.path.exists(path):
                try:
                    txt = open(path, encoding="utf-8-sig").read().strip()
                except Exception:
                    txt = ""
                if txt:
                    m = re.search(r"\b(pass|[A-Ta-t]\s*\d{1,2})\b", txt)
                    if m:
                        mv = m.group(1).replace(" ", "").upper()
                        try:
                            os.remove(path)
                        except Exception:
                            pass
                        return mv
            time.sleep(1)
        return None

    def ai_vs_ai(self):
        """黑读 black_move.txt,白读 white_move.txt,自动对局到双方 pass"""
        self.busy = True
        passes = 0
        while len(self.board.moves) < 400:
            color = "B" if len(self.board.moves) % 2 == 0 else "W"
            f = "black_move.txt" if color == "B" else "white_move.txt"
            self.write_ext_position()
            self.after(0, lambda c=color: self.set_status(
                "🤖 轮到%s —— 请写 %s" % ("黑" if c == "B" else "白", c)))
            mv = self._wait_move(os.path.join(EXT_DIR, f))
            if mv is None:
                self.after(0, lambda: self.set_status("等待着法超时,对局暂停"))
                self.busy = False
                return
            if mv == "PASS":
                self.board.push()
                self.board.moves.append((color, -1, -1))
                passes += 1
                self.after(0, self._ext_refresh)
                if passes >= 2:
                    self.after(0, lambda: self.set_status("双方都停一手 —— 对局结束 ✅"))
                    self.busy = False
                    return
                continue
            passes = 0
            i = COLS.index(mv[0]); j = self.size - int(mv[1:])
            self.board.push()
            ok, cap, err = self.board.try_play(color, i, j)
            if not ok:
                self.board.pop()
                with open(os.path.join(EXT_DIR, "ai_error.txt"), "w", encoding="utf-8") as fh:
                    fh.write("非法着法 %s (%s): %s\n请重新写入 %s\n" % (mv, color, err, f))
                self.after(0, lambda m=mv, e2=err: self.set_status(
                    "❌ %s 非法(%s),已写入 ai_error.txt,请重下" % (m, e2)))
                time.sleep(2)
                continue
            self.board.moves.append((color, i, j))
            self.board.captures[color] += len(cap)
            self.last_move = (i, j)
            if self.engine and self.engine.ok:
                self.engine.play(color, mv)          # 让引擎跟住局面,便于评估
            self.after(0, self._ext_refresh)
            self._ext_eval_async()                   # 实时评估(黑方视角)
        self.busy = False

    def _ext_eval_async(self):
        """AI对AI 模式下也给出引擎评估(黑方视角目差 + 估算胜率 + 候选)"""
        if not (self.engine and self.engine.ok):
            return

        def work():
            color = "B" if len(self.board.moves) % 2 == 0 else "W"
            info = self.engine.analyze(color, secs=1.2, maxmoves=4)
            if not info or info.get("scoreLead") is None:
                return
            lead = info["scoreLead"] if color == "B" else -info["scoreLead"]   # 黑方视角
            wr = disp_wr(lead, self.size)
            cands = info.get("cands") or []

            def upd():
                try:
                    c = self.evalbar
                    c.delete("all")
                    w = c.winfo_width() or 320
                    c.create_rectangle(0, 0, w, 26, fill="#f4f4f4", outline="")
                    c.create_rectangle(0, 0, w * wr, 26, fill="#222", outline="")
                    c.create_text(w / 2, 13, text="黑 %.0f%%" % (wr * 100),
                                  fill="#e53935" if wr < .5 else "#1b7f3a",
                                  font=("Microsoft YaHei", 10, "bold"))
                    self.evaltext.set("黑方领先 %+.1f 目   估算胜率 %.0f%%" % (lead, wr * 100))
                    rows = ["引擎视角(黑方目差):"]
                    for cd in cands[:5]:
                        sl = cd["scoreLead"]
                        v = sl if color == "B" else (-sl if sl is not None else None)
                        rows.append("  %-4s  %s" % (cd["move"], ("%+.1f" % v) if v is not None else "--"))
                    self.candbox.delete("1.0", "end")
                    self.candbox.insert("end", "\n".join(rows))
                except Exception as ex:
                    log("ext eval ui err %s" % ex)
            self.after(0, upd)
        threading.Thread(target=work, daemon=True).start()

    def _ext_refresh(self):
        self.redraw()
        self.refresh_movelist()
        self.save_sgf(silent=True)
        n = len(self.board.moves)
        last = self.board.moves[-1] if self.board.moves else None
        if last:
            mv = "pass" if last[1] < 0 else self.board.coord(last[1], last[2])
            self.set_status("已下 %d 手(最新:%s %s)" % (n, last[0], mv))


    def ai_first_move(self):
        self.busy = True
        self.set_status("AI 先行…")
        mv, info = self.engine.genmove_analyze(self.ai_color(), maxmoves=5)
        if mv:
            i = COLS.index(mv[0].upper())
            j = self.size - int(mv[1:])
            if self.board.g[i][j] == ".":
                self.board.try_play(self.ai_color(), i, j)
            self.board.moves.append((self.ai_color(), i, j))
            self.last_move = (i, j)
            lead = (info or {}).get("scoreLead")
            hl = (-lead) if lead is not None else None
            hw = disp_wr(hl, self.size)
            self.pending_before = hw
            self.after(0, lambda: self._after_ai(mv, hw, hl, info))

    def _revert_last(self):
        """引擎判非法时,撤销玩家刚才那一手"""
        self.board.pop()
        if self.board.moves and self.board.moves[-1][0] == self.human:
            self.board.moves.pop()
        self.last_move = self.board.moves[-1][1:] if self.board.moves else None
        self.busy = False
        self.redraw()
        self.refresh_movelist()
        self.save_sgf(silent=True)
        self.set_status("❌ 这手不合法(打劫禁着点 / 自杀手),已自动撤销 —— 请换个地方下")

    def undo(self):
        if self.busy:
            return
        n = 0
        while n < 2 and self.board.history:
            self.board.pop()
            n += 1
        if self.engine and self.engine.ok:
            for _ in range(n):
                self.engine.undo()
        self.last_move = self.board.moves[-1][1:] if self.board.moves else None
        self.hint_pts = None
        self.redraw()
        self.refresh_movelist()
        self.set_status("已悔棋 %d 手" % n)

    def hint(self):
        if self.busy:
            return
        self.set_status("计算提示…")
        def work():
            info = self.engine.analyze(self.human, secs=1.6, maxmoves=3)
            pts = []
            for cd in (info or {}).get("cands", [])[:3]:
                mv = cd["move"]
                pts.append((COLS.index(mv[0].upper()), self.size - int(mv[1:])))
            self.hint_pts = pts
            self.after(0, self.redraw)
            if pts:
                parts = []
                for k, (L, (i, j)) in enumerate(zip("ABC", pts)):
                    cd = info["cands"][k]
                    sl = cd.get("scoreLead")
                    parts.append("%s:%s(%s)" % (L, self.board.coord(i, j),
                                                ("%+.1f目" % sl) if sl is not None else "?"))
                self.set_status("提示:" + " | ".join(parts))
            else:
                self.set_status("暂无提示")
        threading.Thread(target=work, daemon=True).start()

    def pass_move(self):
        if self.busy:
            return
        self.board.push()
        self.board.moves.append((self.human, -1, -1))
        self.engine.play(self.human, "pass")
        self.set_status("你停一手")
        self.refresh_movelist()
        self.busy = True
        threading.Thread(target=self._after_pass, daemon=True).start()

    def _after_pass(self):
        try:
            mv, info = self.engine.genmove_analyze(self.ai_color(), maxmoves=5)
            if mv and mv.lower() == "pass":
                self.after(0, lambda: self.status.set("AI 也停一手 —— 双方同意可终局(数子)"))
                self.busy = False
                return
            i = COLS.index(mv[0].upper()); j = self.size - int(mv[1:])
            if self.board.g[i][j] == ".":
                self.board.try_play(self.ai_color(), i, j)
            self.board.moves.append((self.ai_color(), i, j))
            self.last_move = (i, j)
            lead = (info or {}).get("scoreLead")
            hl = (-lead) if lead is not None else None
            self.after(0, lambda: self._after_ai(mv, disp_wr(hl, self.size), hl, info))
        except Exception as ex:
            log("pass err %s" % ex)
            self.busy = False

    def resign(self):
        if messagebox.askyesno("认输", "确定认输?"):
            self.set_status("你认输了 —— 想复盘随时说")
            self.save_sgf(silent=False)

    def analyse_now(self):
        if self.busy:
            return
        self.set_status("分析中…")
        def work():
            info = self.engine.analyze(self.human, secs=2.0, maxmoves=5)
            lead = (info or {}).get("scoreLead")
            wr = disp_wr(lead, self.size)
            self.after(0, lambda: self.update_eval(wr, lead, info))
            self.set_status("分析完成")
        threading.Thread(target=work, daemon=True).start()

    def save_sgf(self, silent=True):
        os.makedirs(GAMES, exist_ok=True)
        if not self.sgf_path:
            self.sgf_path = os.path.join(GAMES, "godogo_%s.sgf" %
                                         datetime.datetime.now().strftime("%Y%m%d_%H%M%S"))
        try:
            with open(self.sgf_path, "w", encoding="utf-8") as f:
                f.write(self.board.to_sgf(self.komi))
        except Exception as e:
            log("sgf save failed: %s" % e)
        if not silent:
            messagebox.showinfo("棋谱已保存", self.sgf_path)

    def refresh_movelist(self):
        rows, line = [], []
        for k, (c, i, j) in enumerate(self.board.moves, start=1):
            mv = "pass" if i < 0 else self.board.coord(i, j)
            line.append("%s%-4s" % (c, mv))
            if len(line) == 2:
                rows.append("%3d  %s %s" % (k - 1, line[0], line[1]))
                line = []
        if line:
            rows.append("%3d  %s" % (len(self.board.moves), line[0]))
        cap = "提子: 你 %d / AI %d" % (self.board.captures[self.human], self.board.captures[self.ai_color()])
        self.movelist.delete("1.0", "end")
        self.movelist.insert("end", cap + "\n" + "\n".join(rows))


if __name__ == "__main__":
    log("=== GoDojo start ===")
    try:
        App().mainloop()
    except Exception as e:
        log("fatal: %s\n%s" % (e, traceback.format_exc()))
