# -*- coding: utf-8 -*-
"""GoDojo Web 版 · 本地 HTTP 服务

把对局会话(棋盘 + 引擎 + 外接AI文件协议)包成 JSON API,供 Web 前端调用。
只用标准库(http.server),不引入 web 框架 —— 依赖越少,PyInstaller 打包越省事。

接口一览:
  GET  /                    前端页面(静态资源)
  GET  /api/state           当前完整状态(前端每 250ms 轮询)
  POST /api/new             开新局      {size, human, handicap, opponent, visits}
  POST /api/play            人落子      {coord:"Q16"}
  POST /api/pass            停一手
  POST /api/undo            悔棋(退双方各一手)
  POST /api/hint            提示(A/B/C 推荐点)
  POST /api/analyze         立即分析
  POST /api/resign          认输
  POST /api/visits          调整强度    {visits: 400}
  POST /api/save            保存棋谱
  POST /api/settings        写回引擎/路径设置  {engine:{...}}
  GET  /api/detect          自动探测引擎路径
  POST /api/restart-engine  重启引擎
  POST /api/killstale       清理残留 katago 进程
"""
import os
import re
import sys
import json
import time
import datetime
import threading
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from core import (Board, Engine, load_config, save_config, log, set_log_path,
                  parse_info, disp_wr, handicap_points, detect_engine,
                  katago_processes, kill_stale_engine, LETTERS, COLS, base_dir)


def srv_quit_requested():
    """给工作线程看的退出标志:外壳要求退出时,长轮询循环应尽快让路"""
    return _HB["quit"]


# ---------------- 心跳与退出 ----------------
# 前端每 2 秒 ping 一次;窗口一关心跳就断,外壳据此自动退出后端,
# 不会留下"界面关了但 katago 还在跑"的僵尸进程。
_HB = {"last": 0.0, "seen": False, "quit": False}


def ping():
    _HB["last"] = time.time()
    _HB["seen"] = True


def heartbeat_age():
    """距上次心跳的秒数;从未收到过心跳则返回 None"""
    if not _HB["seen"]:
        return None
    return time.time() - _HB["last"]


def request_quit():
    _HB["quit"] = True


def quit_requested():
    return _HB["quit"]


def reset_heartbeat():
    _HB["last"] = 0.0
    _HB["seen"] = False
    _HB["quit"] = False


def web_dir():
    """前端资源目录,按优先级找:
      1) exe / 源码根目录旁边的 web\\  —— 放在外面,改界面不用重新打包
      2) 打包进 exe 的资源(_MEIPASS)
      3) 源码里的 webapp\\web
    """
    ext = os.path.join(base_dir(), "web")
    if os.path.isfile(os.path.join(ext, "index.html")):
        return ext
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        p = os.path.join(sys._MEIPASS, "web")
        if os.path.isdir(p):
            return p
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "web")


# ---------------- 对局会话 ----------------

class GameSession(object):
    def __init__(self, cfg):
        self.cfg = cfg
        self.lock = threading.RLock()

        g = cfg.get("game", {})
        self.size = int(g.get("size", 19))
        self.human = g.get("human", "B")
        self.handicap = int(g.get("handicap", 0))
        self.visits = int(g.get("visits", 120))
        self.opponent = "ai"                       # ai | external | both
        self.komi = 0.5 if self.handicap > 0 else float(g.get("komi", 7.5))

        self.board = Board(self.size)
        self.engine = None
        self.engine_ready = False
        self.engine_msg = "引擎启动中…"
        self.busy = False
        self.status = "正在加载引擎,请稍候…"
        self.ev = {"winrate": None, "lead": None, "cands": [], "pv": ""}
        self.last_move = None
        self.hint_pts = []
        self.coach = ""
        self.sgf_path = None
        self.game_over = False
        self.pending_before = None
        self.handicap_pts = handicap_points(self.size, self.handicap) if self.handicap > 0 else []
        self.boot_engine()

    # ---- 引擎 ----
    def boot_engine(self):
        def work():
            self.engine = Engine(self.cfg)
            with self.lock:
                self.engine_ready = self.engine.ok
                self.engine_msg = ("引擎就绪[%s]" % self.engine.label if self.engine.ok
                                   else "引擎启动失败: %s" % self.engine.err)
            if self.engine.ok:
                self.engine.setup(self.size, self.komi)
                self.engine.set_visits(self.visits)
                self.set_status("引擎就绪 ✅  你执%s,点棋盘落子"
                                % ("黑" if self.human == "B" else "白"))
            else:
                self.set_status(self.engine_msg)
        threading.Thread(target=work, daemon=True).start()
        # 首次在新机器上跑 GPU 引擎要现场调优(5-10 分钟),期间引擎不会应答。
        # 起个看门线程把 Engine.progress 搬到 status 上,界面才有个活着的提示。
        threading.Thread(target=self._watch_boot, daemon=True).start()

    def _watch_boot(self):
        """启动期间把引擎进度显示到状态行(引擎就绪或失败后自动停)"""
        t0 = time.time()
        while time.time() - t0 < 1000:
            time.sleep(2)
            if self.engine and self.engine.ok:
                return
            if self.engine and self.engine.err:
                return
            p = self.engine.progress if self.engine else ""
            if p:
                self.set_status("⏳ " + p)

    def restart_engine(self):
        def work():
            with self.lock:
                self.set_status("正在重启引擎…")
                self.engine_ready = False
            if self.engine is None:
                self.engine = Engine(self.cfg)
            else:
                self.engine.restart()
            if self.engine.ok:
                self.engine.setup(self.size, self.komi)
                self.engine.set_visits(self.visits)
                self.resync_engine()
            with self.lock:
                self.engine_ready = self.engine.ok
                self.engine_msg = "引擎就绪" if self.engine.ok else "引擎启动失败: %s" % self.engine.err
            self.set_status(("引擎已重启 ✅" if self.engine.ok else self.engine_msg)
                            + ("  [%s]" % self.engine.label if self.engine.ok and self.engine.label else ""))
        threading.Thread(target=work, daemon=True).start()
        return True

    def resync_engine(self):
        """按当前着法历史重建引擎盘面(含让子座子;带 pass 着法)"""
        if not (self.engine and self.engine.ok):
            return
        moves = [(c, "pass" if i < 0 else self.board.coord(i, j))
                 for (c, i, j) in self.board.moves]
        self.engine.resync(moves)

    def set_status(self, s):
        with self.lock:
            self.status = s

    # ---- 状态快照 ----
    def state(self):
        with self.lock:
            b = self.board
            grid = [[0 if v == "." else (1 if v == "B" else 2) for v in row] for row in b.g]
            moves = [["B" if c == "B" else "W", ("pass" if i < 0 else b.coord(i, j))]
                     for (c, i, j) in b.moves]
            procs = katago_processes() if self._should_probe_procs() else None
            return {
                "size": self.size,
                "komi": self.komi,
                "handicap": self.handicap,
                "human": self.human,
                "opponent": self.opponent,
                "visits": self.visits,
                "turn": self.side_to_move(),
                "grid": grid,
                "moves": moves,
                "captures": {"human": b.captures[self.human], "ai": b.captures[self.ai_color()]},
                "last_move": list(self.last_move) if self.last_move else None,
                "hint": [list(p) for p in self.hint_pts],
                "busy": self.busy,
                "status": self.status,
                "coach": self.coach,
                "eval": self.ev,
                "game_over": self.game_over,
                "engine": {
                    "ready": self.engine_ready,
                    "msg": self.engine_msg,
                    "alive": bool(self.engine and self.engine.alive()),
                    "label": (self.engine.label if self.engine else ""),
                    "tries": (list(self.engine.notes) if self.engine else []),
                    "progress": (self.engine.progress if self.engine else ""),
                    "katago": self.cfg.get("engine", {}).get("katago", ""),
                    "paths": {k: self.cfg.get("engine", {}).get(k, "")
                              for k in ("katago", "model", "config")},
                    "procs": procs,
                },
                "sgf": self.sgf_path or "",
                "ext_dir": self.cfg.get("paths", {}).get("external", ""),
            }

    _proc_tick = [0]

    def _should_probe_procs(self):
        """每约 2 秒探测一次残留进程即可,不必每次轮询都调 tasklist"""
        self._proc_tick[0] = (self._proc_tick[0] + 1) % 8
        return self._proc_tick[0] == 0

    def side_to_move(self):
        """当前该谁走(让子局白先行 —— 不能用奇偶判断)"""
        if not self.board.moves:
            return "W" if self.handicap > 0 else "B"
        return "W" if self.board.moves[-1][0] == "B" else "B"

    def ai_color(self):
        return "W" if self.human == "B" else "B"

    # ---- 开局 ----
    def new_game(self, size=None, human=None, handicap=None, opponent=None, visits=None):
        with self.lock:
            if size is not None:
                self.size = int(size)
            if human is not None:
                self.human = "B" if str(human).upper().startswith("B") else "W"
            if handicap is not None:
                self.handicap = int(handicap)
            if opponent is not None:
                self.opponent = opponent
            if visits is not None:
                self.visits = int(visits)

            self.komi = 0.5 if self.handicap > 0 else 7.5
            self.board = Board(self.size)
            self.last_move = None
            self.hint_pts = []
            self.coach = ""
            self.game_over = False
            self.pending_before = None
            self.handicap_pts = handicap_points(self.size, self.handicap) if self.handicap > 0 else []
            self.ev = {"winrate": None, "lead": None, "cands": [], "pv": ""}
            self.sgf_path = None            # 新局 -> 换新棋谱文件,避免覆盖

            if self.handicap > 0:
                for (i, j) in handicap_points(self.size, self.handicap):
                    ok, cap, err = self.board.try_play("B", i, j)
                    if ok:
                        self.board.moves.append(("B", i, j))
                        self.last_move = (i, j)
                log("new game: %d路 让%d子 komi %.1f" % (self.size, self.handicap, self.komi))
            else:
                log("new game: %d路 分先 komi %.1f" % (self.size, self.komi))

            ext = self.cfg.get("paths", {}).get("external", "")
            if self.opponent in ("external", "both"):
                for f in ("ai_move.txt", "ai_error.txt", "black_move.txt", "white_move.txt"):
                    try:
                        os.remove(os.path.join(ext, f))
                    except Exception:
                        pass
            self.save_sgf()

        if self.opponent in ("external", "both"):
            self.write_ext_position()

        if self.opponent == "both":
            self.set_status("🤖 AI对AI:黑写 black_move.txt,白写 white_move.txt")
            threading.Thread(target=self._ai_vs_ai, daemon=True).start()
            return True

        # 刷新引擎盘面并重置强度
        def prep():
            if not (self.engine and self.engine.ok):
                return
            self.engine.setup(self.size, self.komi)
            self.engine.set_visits(self.visits)
            if self.handicap > 0:
                for (i, j) in handicap_points(self.size, self.handicap):
                    self.engine.play("B", self.board.coord(i, j))
            if self.human == "W" or self.handicap > 0:      # 让子局白方(AI)先行
                if self.opponent == "external":
                    self._ext_turn()
                else:
                    self._ai_first_move()
            else:
                self.set_status("新局开始:你执黑先下")
        threading.Thread(target=prep, daemon=True).start()
        return True

    # ---- 人落子 ----
    def human_play(self, coord):
        coord = (coord or "").strip().upper()
        m = re.fullmatch(r"([A-HJ-T])(\d{1,2})", coord)
        if not m:
            return False, "坐标格式不对(例:Q16 / E5)"
        with self.lock:
            if self.busy:
                return False, "引擎正在思考,稍候"
            if self.game_over:
                return False, "本局已结束,请开新局"
            if not (self.engine and self.engine.ok):
                return False, "引擎未就绪"
            if self.opponent == "both":
                return False, "AI对AI 模式下不能手动落子"
            col = LETTERS.index(m.group(1))
            row = self.size - int(m.group(2))
            if col >= self.size or not (0 <= row < self.size):
                return False, "坐标超出 %d 路棋盘" % self.size
            if self.side_to_move() != self.human:
                return False, "现在不是你的回合"
            if self.board.g[col][row] != ".":
                return False, "该点已有子"
            self.board.push()
            ok, cap, err = self.board.try_play(self.human, col, row)
            if not ok:
                self.board.pop()
                return False, err
            self.board.moves.append((self.human, col, row))
            self.board.captures[self.human] += len(cap)
            self.last_move = (col, row)
            self.hint_pts = []
            self.busy = True
            self.set_status("你下 %s%s" % (coord, "(提%d子)" % len(cap) if cap else ""))
        self.save_sgf()
        threading.Thread(target=self._after_human, args=(coord,), daemon=True).start()
        return True, ""

    def _after_human(self, coord):
        try:
            e = self.engine
            if not (e and e.ok):
                with self.lock:
                    self.busy = False
                return
            if not e.play(self.human, coord):
                # 引擎判非法(通常是打劫) -> 撤销这一手,提示重下
                with self.lock:
                    self.board.pop()
                    if self.board.moves and self.board.moves[-1][0] == self.human:
                        self.board.moves.pop()
                    self.last_move = self.board.moves[-1][1:] if self.board.moves else None
                    self.busy = False
                    self.set_status("❌ 这手不合法(打劫禁着点 / 自杀手),已自动撤销 —— 请换个地方下")
                self.resync_engine()
                self.save_sgf()
                return

            with self.lock:
                opp = self.opponent

            # 1) 讲评你这一手(所有对手模式都做;外接模式下这是唯一引擎交互)
            self._coach_after_human(coord)

            # 2) 对手应手
            if opp == "external":
                self._ext_turn()
                return
            mv, info = e.genmove_analyze(self.ai_color(), maxmoves=5, interval=100)
            self._apply_ai_move(mv, info)
        except Exception as ex:
            log("after_human error: %s\n%s" % (ex, traceback.format_exc()))
            with self.lock:
                self.busy = False
                self.status = "出错: %s" % ex

    def _coach_after_human(self, coord):
        """分析你刚下的这手,生成讲评(不改变 busy 状态)"""
        e = self.engine
        if not (e and e.ok):
            return
        try:
            info_ai = e.analyze(self.ai_color(), secs=1.2, maxmoves=5)
        except Exception as ex:
            log("coach analyze failed: %s" % ex)
            return
        lead_ai_a = info_ai.get("scoreLead") if info_ai else None
        human_wr = disp_wr(-lead_ai_a, self.size) if lead_ai_a is not None else None
        with self.lock:
            prev = self.pending_before
        if human_wr is not None and prev is not None:
            delta = (human_wr - prev) * 100
            best = ", ".join(c["move"] for c in (info_ai or {}).get("cands", [])[:3])
            if delta < -12:
                msg = "⚠️ 这手掉了 %.0f%% 胜率;引擎推荐:%s" % (-delta, best)
            elif delta < -4:
                msg = "🙂 这手稍缓(%.0f%%),推荐:%s" % (delta, best)
            else:
                msg = "✅ 好手!胜率 %.0f%%(推荐点:%s)" % (human_wr * 100, best)
            with self.lock:
                self.coach = msg

    def _apply_ai_move(self, mv, info):
        """把 AI 的着法落到棋盘并更新面板"""
        if not mv or mv.lower() in ("pass", "resign"):
            with self.lock:
                self.busy = False
                self.set_status("AI:%s" % (mv or "无应手"))
            return
        mv = mv.upper()
        if not re.fullmatch(r"[A-HJ-T]\d{1,2}", mv):
            with self.lock:
                self.busy = False
                self.set_status("AI 返回了异常着法:%s" % mv)
            return
        i = COLS.index(mv[0])
        j = self.size - int(mv[1:])
        with self.lock:
            if not (0 <= i < self.size and 0 <= j < self.size) or self.board.g[i][j] != ".":
                self.busy = False
                self.set_status("AI 落子异常(%s),已跳过" % mv)
                return
            cap = []
            ok, cap, err = self.board.try_play(self.ai_color(), i, j)
            if not ok:
                self.busy = False
                self.set_status("AI 落子异常(%s),已跳过" % err)
                return
            self.board.moves.append((self.ai_color(), i, j))
            self.board.captures[self.ai_color()] += len(cap)
            self.last_move = (i, j)
            lead_ai = (info or {}).get("scoreLead")
            lead_human = (-lead_ai) if lead_ai is not None else None
            human_wr2 = disp_wr(lead_human, self.size) if lead_human is not None else None
            self.pending_before = human_wr2
            self.ev = {
                "winrate": human_wr2,
                "lead": lead_human,
                "cands": (info or {}).get("cands", []),
                "pv": (info or {}).get("pv", ""),
            }
            self.busy = False
            self.set_status("AI 下 %s ✅  轮到你" % mv)
        self.save_sgf()

    def _ai_first_move(self):
        with self.lock:
            self.busy = True
            self.set_status("AI 先行…")
        mv, info = self.engine.genmove_analyze(self.ai_color(), maxmoves=5)
        self._apply_ai_move(mv, info)

    # ---- 其它操作 ----
    def pass_move(self):
        with self.lock:
            if self.busy or self.game_over or not (self.engine and self.engine.ok):
                return False, "当前不能停一手"
            if self.opponent == "both":
                return False, "AI对AI 模式不支持手动停一手"
            self.board.push()
            self.board.moves.append((self.human, -1, -1))
            self.busy = True
            self.set_status("你停一手")
        self.save_sgf()
        self.engine.play(self.human, "pass")

        def work():
            if self.opponent == "external":
                # 外接 AI 模式:停一手后轮到外接 AI,不该由内置引擎抢着应手
                self._ext_turn()
                return
            mv, info = self.engine.genmove_analyze(self.ai_color(), maxmoves=5)
            if mv and mv.lower() == "pass":
                with self.lock:
                    self.busy = False
                    self.game_over = True
                    self.set_status("双方各停一手 —— 对局结束(可数子 / 复盘)")
                return
            self._apply_ai_move(mv, info)
        threading.Thread(target=work, daemon=True).start()
        return True, ""

    def undo(self):
        with self.lock:
            if self.busy:
                return False, "引擎思考中,稍候再悔棋"
            n = 0
            while n < 2 and self.board.history:
                self.board.pop()
                n += 1
            if n == 0:
                return False, "没有可悔的棋"
            self.last_move = self.board.moves[-1][1:] if self.board.moves else None
            self.hint_pts = []
            self.set_status("已悔棋 %d 手" % n)
        if self.engine and self.engine.ok:
            self.resync_engine()          # 直接按着法历史重建,undo 调用次数不可靠
        self.save_sgf()
        return True, ""

    def hint(self):
        with self.lock:
            if self.busy or not (self.engine and self.engine.ok):
                return False, "当前不能提示"

        def work():
            info = self.engine.analyze(self.human, secs=1.6, maxmoves=3)
            pts = []
            for cd in (info or {}).get("cands", [])[:3]:
                mv = cd["move"]
                pts.append((LETTERS.index(mv[0].upper()), self.size - int(mv[1:])))
            parts = []
            for k, (i, j) in enumerate(pts):
                cd = info["cands"][k]
                sl = cd.get("scoreLead")
                parts.append("%s:%s(%s)" % ("ABC"[k], self.board.coord(i, j),
                                            ("%+.1f目" % sl) if sl is not None else "?"))
            with self.lock:
                self.hint_pts = pts
                self.set_status(("提示:" + " | ".join(parts)) if pts else "暂无提示")
        threading.Thread(target=work, daemon=True).start()
        return True, ""

    def analyse(self):
        with self.lock:
            if self.busy or not (self.engine and self.engine.ok):
                return False, "当前不能分析"
            self.set_status("分析中…")

        def work():
            info = self.engine.analyze(self.human, secs=2.0, maxmoves=5)
            lead = (info or {}).get("scoreLead")
            wr = disp_wr(lead, self.size)
            with self.lock:
                self.ev = {"winrate": wr, "lead": lead,
                           "cands": (info or {}).get("cands", []),
                           "pv": (info or {}).get("pv", "")}
                self.set_status("分析完成")
        threading.Thread(target=work, daemon=True).start()
        return True, ""

    def resign(self):
        with self.lock:
            self.game_over = True
            self.set_status("你认输了 —— 想复盘随时说")
        self.save_sgf()
        return True, ""

    def set_visits(self, n):
        with self.lock:
            self.visits = int(n)
        if self.engine and self.engine.ok:
            threading.Thread(target=lambda: self.engine.set_visits(self.visits), daemon=True).start()
        return True, ""

    def save_sgf(self):
        try:
            games = self.cfg.get("paths", {}).get("games", "")
            if not games:
                return None
            os.makedirs(games, exist_ok=True)
            if not self.sgf_path:
                self.sgf_path = os.path.join(
                    games, "godogo_%s.sgf" % datetime.datetime.now().strftime("%Y%m%d_%H%M%S"))
            with open(self.sgf_path, "w", encoding="utf-8") as f:
                f.write(self.board.to_sgf(self.komi, self.handicap))
        except Exception as e:
            log("sgf save failed: %s" % e)
        return self.sgf_path

    # ---- 外接 AI(文件接口)----
    def write_ext_position(self):
        ext = self.cfg.get("paths", {}).get("external", "")
        os.makedirs(ext, exist_ok=True)
        with self.lock:
            b, size = self.board, self.size
            L = ["=== 围棋对局 · 外接AI 接口 ===",
                 "棋盘: %d 路   贴目: %.1f   当前第 %d 手" % (size, self.komi, len(b.moves)),
                 ""]
            if self.opponent == "both":
                nxt0 = "黑" if len(b.moves) % 2 == 0 else "白"
                L.append("对局双方: 黑 = 本机   白 = 外部AI")
                L.append("现在轮到: %s" % nxt0)
            else:
                L.append("你(外接AI)执: %s     对手(GoDojo内置KataGo)执: %s" %
                         ("黑" if self.ai_color() == "B" else "白",
                          "黑" if self.human == "B" else "白"))
            L += ["",
                  "局面(行号从下往上 1..%d,列 A..%s;X = 黑子,O = 白子,. = 空点):" % (
                      size, LETTERS[size - 1]),
                  "      " + " ".join(LETTERS[i] for i in range(size))]
            for j in range(size):
                row = []
                for i in range(size):
                    v = b.g[i][j]
                    row.append("." if v == "." else ("X" if v == "B" else "O"))
                L.append("%4d  %s" % (size - j, " ".join(row)))
            L += ["",
                  "着法历史: " + ",".join(
                      ("B" if c == "B" else "W") + b.coord(i, j)
                      for (c, i, j) in b.moves if i >= 0),
                  ""]
            empt = [b.coord(i, j) for j in range(size) for i in range(size) if b.g[i][j] == "."]
            L.append("空点(%d 个): %s" % (len(empt), " ".join(empt)))
            L.append("")
            if self.opponent == "both":
                nxt = "B" if len(b.moves) % 2 == 0 else "W"
                f = "black_move.txt" if nxt == "B" else "white_move.txt"
                L.append(">>> 现在轮到: %s" % ("黑" if nxt == "B" else "白"))
                L.append(">>> 请把着法写入: %s" % os.path.join(ext, f))
                L.append(">>> 只写一个坐标(如 E5),停一手写 pass")
            else:
                L.append(">>> 请把你的下一手写入文件: %s" % os.path.join(ext, "ai_move.txt"))
                L.append(">>> 只写一个坐标即可,例如: E5   (停一手写 pass)")
        with open(os.path.join(ext, "position.txt"), "w", encoding="utf-8") as f:
            f.write("\n".join(L))

    def _ext_turn(self):
        """轮到外接AI:写局面 + 轮询它的着法(最多等 60 分钟)"""
        ext = self.cfg.get("paths", {}).get("external", "")
        with self.lock:
            self.busy = True
        self.write_ext_position()
        self.set_status("⏳ 轮到外接AI —— 请让它读 position.txt,并把着法写入 ai_move.txt")
        mf = os.path.join(ext, "ai_move.txt")
        ef = os.path.join(ext, "ai_error.txt")
        try:
            if os.path.exists(ef):
                os.remove(ef)
        except Exception:
            pass
        mv = None
        for _ in range(3600):
            if srv_quit_requested():
                return
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
            with self.lock:
                self.busy = False
                self.set_status("外接AI 超时未落子")
            return
        if mv == "PASS":
            with self.lock:
                self.board.push()
                self.board.moves.append((self.ai_color(), -1, -1))
                self.busy = False
                self.set_status("外接AI 停一手 —— 轮到你")
            if self.engine and self.engine.ok:
                self.engine.play(self.ai_color(), "pass")     # 同步给内置引擎
            self.save_sgf()
            self.write_ext_position()
            return
        i, j = COLS.index(mv[0]), self.size - int(mv[1:])
        illegal = False
        with self.lock:
            self.board.push()
            ok, cap, err = self.board.try_play(self.ai_color(), i, j)
            if not ok:
                self.board.pop()
                illegal = True
                try:
                    with open(ef, "w", encoding="utf-8") as f:
                        f.write("非法着法 %s: %s\n请重新把着法写入 ai_move.txt\n" % (mv, err))
                except Exception:
                    pass
                self.busy = False
                self.set_status("外接AI 的着法非法(%s),已写入 ai_error.txt,请重下" % err)
            else:
                self.board.moves.append((self.ai_color(), i, j))
                self.board.captures[self.ai_color()] += len(cap)
                self.last_move = (i, j)
                self.busy = False
                self.set_status("外接AI 下 %s%s ✅  轮到你"
                                % (mv, "(提%d子)" % len(cap) if cap else ""))
        if not illegal and self.engine and self.engine.ok:
            if not self.engine.play(self.ai_color(), mv):
                self.resync_engine()      # 引擎不认(盘面脱节) -> 全量重建
        self.save_sgf()
        self.write_ext_position()
        if illegal:
            threading.Thread(target=self._ext_turn, daemon=True).start()

    def _ai_vs_ai(self):
        """黑读 black_move.txt,白读 white_move.txt,自动对局到双方 pass"""
        ext = self.cfg.get("paths", {}).get("external", "")
        with self.lock:
            self.busy = True
        passes = 0
        while True:
            if srv_quit_requested():
                with self.lock:
                    self.busy = False
                return
            with self.lock:
                if len(self.board.moves) >= 400:
                    self.busy = False
                    return
                color = "B" if len(self.board.moves) % 2 == 0 else "W"
            f = "black_move.txt" if color == "B" else "white_move.txt"
            self.write_ext_position()
            self.set_status("🤖 轮到%s —— 请写 %s" % ("黑" if color == "B" else "白", f))
            mv = self._wait_move(os.path.join(ext, f))
            if mv is None:
                with self.lock:
                    self.busy = False
                    self.set_status("等待着法超时,对局暂停")
                return
            if mv == "PASS":
                with self.lock:
                    self.board.push()
                    self.board.moves.append((color, -1, -1))
                passes += 1
                self.save_sgf()
                if passes >= 2:
                    with self.lock:
                        self.busy = False
                        self.game_over = True
                        self.set_status("双方都停一手 —— 对局结束 ✅")
                    return
                continue
            passes = 0
            i, j = COLS.index(mv[0]), self.size - int(mv[1:])
            with self.lock:
                self.board.push()
                ok, cap, err = self.board.try_play(color, i, j)
                if not ok:
                    self.board.pop()
                    try:
                        with open(os.path.join(ext, "ai_error.txt"), "w", encoding="utf-8") as fh:
                            fh.write("非法着法 %s (%s): %s\n请重新写入 %s\n" % (mv, color, err, f))
                    except Exception:
                        pass
                    self.set_status("❌ %s 非法(%s),已写入 ai_error.txt,请重下" % (mv, err))
                else:
                    self.board.moves.append((color, i, j))
                    self.board.captures[color] += len(cap)
                    self.last_move = (i, j)
            if not ok:
                time.sleep(2)
                continue
            self.save_sgf()
            if self.engine and self.engine.ok:
                try:
                    if not self.engine.play(color, mv):
                        self.resync_engine()
                except Exception:
                    pass

    @staticmethod
    def _wait_move(path, timeout=3600):
        for _ in range(timeout):
            if srv_quit_requested():
                return None
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


# ---------------- HTTP 层 ----------------

MIME = {".html": "text/html; charset=utf-8", ".js": "application/javascript; charset=utf-8",
        ".css": "text/css; charset=utf-8", ".json": "application/json; charset=utf-8",
        ".svg": "image/svg+xml", ".png": "image/png", ".ico": "image/x-icon",
        ".woff2": "font/woff2", ".txt": "text/plain; charset=utf-8"}


class Handler(BaseHTTPRequestHandler):
    session = None
    cfg = None
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        pass                                   # 静音访问日志,避免刷屏

    # ---- 输出辅助 ----
    def _send(self, code, body, ctype="application/json; charset=utf-8"):
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        try:
            self.wfile.write(body)
        except Exception:
            pass

    def _json(self, obj, code=200):
        self._send(code, json.dumps(obj, ensure_ascii=False))

    def _body(self):
        try:
            n = int(self.headers.get("Content-Length") or 0)
            if n <= 0:
                return {}
            return json.loads(self.rfile.read(n).decode("utf-8"))
        except Exception:
            return {}

    # ---- 路由 ----
    def do_GET(self):
        path = self.path.split("?")[0]
        # 记录页面/静态资源请求(排除高频轮询),用于确认浏览器到底有没有来取页面
        if path != "/api/state":
            log("GET %s" % path)
        try:
            if path == "/api/state":
                return self._json(self.session.state())
            if path == "/api/detect":
                newcfg = dict(self.cfg)
                return self._json(detect_engine(self.cfg))
            if path in ("/", "/index.html"):
                return self._static("index.html")
            return self._static(path.lstrip("/"))
        except Exception as e:
            log("GET %s err %s\n%s" % (path, e, traceback.format_exc()))
            return self._json({"error": str(e)}, 500)

    def do_POST(self):
        path = self.path.split("?")[0]
        d = self._body()
        try:
            s = self.session
            if path == "/api/new":
                s.new_game(size=d.get("size"), human=d.get("human"),
                           handicap=d.get("handicap"), opponent=d.get("opponent"),
                           visits=d.get("visits"))
                return self._json({"ok": True})
            if path == "/api/play":
                ok, err = s.human_play(d.get("coord", ""))
                return self._json({"ok": ok, "error": err})
            if path == "/api/pass":
                ok, err = s.pass_move()
                return self._json({"ok": ok, "error": err})
            if path == "/api/undo":
                ok, err = s.undo()
                return self._json({"ok": ok, "error": err})
            if path == "/api/hint":
                ok, err = s.hint()
                return self._json({"ok": ok, "error": err})
            if path == "/api/analyze":
                ok, err = s.analyse()
                return self._json({"ok": ok, "error": err})
            if path == "/api/resign":
                ok, err = s.resign()
                return self._json({"ok": ok, "error": err})
            if path == "/api/visits":
                ok, err = s.set_visits(d.get("visits", 120))
                return self._json({"ok": ok, "error": err})
            if path == "/api/save":
                return self._json({"ok": True, "path": s.save_sgf()})
            if path == "/api/restart-engine":
                s.restart_engine()
                return self._json({"ok": True})
            if path == "/api/ping":
                ping()
                return self._json({"ok": True, "age": 0})
            if path == "/api/quit":
                request_quit()
                return self._json({"ok": True})
            if path == "/api/diag":
                log("DIAG %s" % json.dumps(d, ensure_ascii=False))
                return self._json({"ok": True})
            if path == "/api/killstale":
                ok, msg = kill_stale_engine()
                return self._json({"ok": ok, "msg": msg})
            if path == "/api/settings":
                eng = d.get("engine") or {}
                for k in ("katago", "model", "config"):
                    if eng.get(k):
                        self.cfg["engine"][k] = eng[k]
                # 只回写引擎组:settings 弹窗只编辑引擎路径,
                # 整个 self.cfg 落盘会把本次会话的运行态(如 ports=0)一并固化
                save_config({"engine": self.cfg["engine"]})
                return self._json({"ok": True, "config": self.cfg, "notes": detect_engine(self.cfg)["notes"]})
            return self._json({"error": "unknown endpoint"}, 404)
        except Exception as e:
            log("POST %s err %s\n%s" % (path, e, traceback.format_exc()))
            return self._json({"ok": False, "error": str(e)}, 500)

    def _static(self, rel):
        rel = rel.replace("\\", "/").lstrip("/")
        if ".." in rel:
            return self._json({"error": "forbidden"}, 403)
        root = web_dir()
        p = os.path.join(root, rel.replace("/", os.sep))
        if not os.path.isfile(p):
            return self._json({"error": "not found: " + rel}, 404)
        ext = os.path.splitext(p)[1].lower()
        with open(p, "rb") as f:
            data = f.read()
        return self._send(200, data, MIME.get(ext, "application/octet-stream"))


def start_server(cfg=None, port=None):
    """启动本地服务;返回 (server, port, thread)"""
    cfg = cfg or load_config()
    set_log_path(cfg.get("paths", {}).get("log"))

    Handler.cfg = cfg
    Handler.session = GameSession(cfg)

    host = cfg.get("server", {}).get("host", "127.0.0.1")
    want = port if port is not None else int(cfg.get("server", {}).get("port", 0))
    srv = ThreadingHTTPServer((host, want), Handler)
    srv.daemon_threads = True
    real_port = srv.server_address[1]
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    log("web server on http://%s:%d  (web=%s)" % (host, real_port, web_dir()))
    return srv, real_port, t


if __name__ == "__main__":
    cfg = load_config()
    srv, port, _ = start_server(cfg)
    print("GoDojo Web 已启动: http://127.0.0.1:%d" % port)
    print("按 Ctrl+C 退出")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nbye")
