# -*- coding: utf-8 -*-
"""白方快速应手:轮到我(外接AI/白)时自动算一手并写入 ai_move.txt
策略:本地 KataGo(低 visits 求快),每手 2-5 秒
"""
import os, re, time, importlib.util

EXT = r"F:\围棋\外接AI"
POS = os.path.join(EXT, "position.txt")
MV = os.path.join(EXT, "ai_move.txt")
LOG = os.path.join(EXT, "auto_white.log")
MAXV = 40

spec = importlib.util.spec_from_file_location("gd", r"F:\围棋\GoDojo.py")
gd = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gd)
L2C = "ABCDEFGHJKLMNOPQRST"


def logm(s):
    with open(LOG, "a", encoding="utf-8") as f:
        f.write("%s %s\n" % (time.strftime("%H:%M:%S"), s))


def read_pos():
    try:
        t = open(POS, encoding="utf-8").read()
    except Exception:
        return None
    size = int(re.search(r"棋盘:\s*(\d+)\s*路", t).group(1))
    n = int(re.search(r"当前第\s*(\d+)\s*手", t).group(1))
    hist = re.search(r"着法历史:\s*(.*)", t)
    moves = []
    if hist and hist.group(1).strip():
        for tok in hist.group(1).split(","):
            tok = tok.strip()
            m = re.match(r"([BW])\s*([A-T])(\d{1,2})", tok)
            if m:
                moves.append((m.group(1), m.group(2) + m.group(3)))
    return size, n, moves


def main():
    logm("=== auto_white start (maxVisits=%d) ===" % MAXV)
    e = gd.Engine()
    if not e.ok:
        logm("engine failed: %s" % e.err)
        return
    size, komi = 9, 7.5
    e.setup(size, komi)
    e.cmd("kata-set-param maxVisits %d" % MAXV)
    fed = 0
    while True:
        try:
            r = read_pos()
            if not r:
                time.sleep(0.5); continue
            sz, n, moves = r
            if sz != size:
                size = sz
                e.setup(size, komi)
                e.cmd("kata-set-param maxVisits %d" % MAXV)
                fed = 0
            # 同步引擎盘面
            if n < fed or (n >= 1 and fed >= 1 and len(moves) < fed):
                e.setup(size, komi)
                e.cmd("kata-set-param maxVisits %d" % MAXV)
                fed = 0
            while fed < len(moves):
                c, mv = moves[fed]
                e.play(c, mv)
                fed += 1
            # 轮到我? (白走:已下奇数手)
            if n % 2 == 1 and not os.path.exists(MV):
                color = "W" if n % 2 == 1 else "B"
                t0 = time.time()
                mv, info = e.genmove_analyze(color, maxmoves=3, interval=40)
                el = time.time() - t0
                if mv and mv.lower() not in ("pass", "resign"):
                    with open(MV, "w", encoding="utf-8") as f:
                        f.write(mv)
                    fed += 1
                    lead = (info or {}).get("scoreLead")
                    logm("第%d手: 我(W) 下 %s  (%.1fs, 引擎目差(白视角) %s)" % (
                        n + 1, mv, el, ("%+.1f" % lead) if lead is not None else "?"))
                else:
                    logm("引擎返回 %s,跳过" % mv)
            time.sleep(0.4)
        except Exception as ex:
            logm("err %s" % ex)
            time.sleep(1)


if __name__ == "__main__":
    main()
