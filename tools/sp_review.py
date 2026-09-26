# -*- coding: utf-8 -*-
"""自战复盘:逐手评估,找出形势大幅波动的关键手(赛后用)。

用法: python -u sp_review.py <session目录> [每手分析秒数]
做法: 用一个 KataGo 会话,从空盘重放,每 N 手(默认每 10 手)做一次限时分析,
      记录白方目差,输出波动最大的若干手 —— 即"转折点"。
"""
import json, os, re, subprocess, sys, threading, time

KG = r"F:\围棋\KataGo-opencl"
NET = os.path.join(KG, "kata1-tf3-b11c768-s11500M-d6163M.bin.gz")
CFG = os.path.join(KG, "gtp_play.cfg")


def main():
    session = sys.argv[1]
    every = int(sys.argv[2]) if len(sys.argv) > 2 else 10
    each = float(sys.argv[3]) if len(sys.argv) > 3 else 3.0
    d = json.load(open(os.path.join(session, "moves.json"), encoding="utf-8"))
    moves = [m for m in d["moves"] if m["coord"].upper() not in ("PASS", "RESIGN")]

    p = subprocess.Popen([os.path.join(KG, "katago.exe"), "gtp", "-model", NET, "-config", CFG],
                         stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                         cwd=KG, universal_newlines=True, encoding="utf-8", errors="replace", bufsize=1)
    lines = []
    threading.Thread(target=lambda: [lines.append(l.rstrip("\r\n")) for l in p.stdout], daemon=True).start()

    def gtp(c, timeout=90):
        lines.clear(); p.stdin.write(c + "\n"); p.stdin.flush()
        t0 = time.time()
        while time.time() - t0 < timeout:
            if lines and lines[-1].strip() == "":
                break
            time.sleep(0.03)
        return [x for x in lines if x.strip()]

    def analyze(side, secs):
        lines.clear()
        p.stdin.write("kata-analyze %s interval 200 maxmoves 1\n" % side); p.stdin.flush()
        t0 = time.time(); best = ""
        while time.time() - t0 < secs:
            time.sleep(0.3)
            c = [l for l in lines if l.startswith("info ") and "scoreLead" in l]
            if c:
                best = c[-1]
        m = re.search(r"scoreLead (-?[0-9.]+)", best)
        v = re.search(r"visits (\d+)", best)
        if not m:
            return None, None
        s = float(m.group(1))
        return (s if side == "w" else -s), (v.group(1) if v else None)

    gtp("boardsize %d" % d["size"]); gtp("komi %g" % d["komi"])
    gtp("kata-set-param maxVisits 400")
    curve = []
    for i, m in enumerate(moves, 1):
        gtp("play %s %s" % (m["color"], m["coord"]))
        if i % every == 0 or i == len(moves):
            side = "b" if i % 2 == 0 else "w"
            s, v = analyze(side, each)
            curve.append({"move": i, "scoreLead_white": s, "visits": v})
            print("  第%3d手 白目差 %s" % (i, ("%+.1f" % s) if s is not None else "?"), flush=True)
    # 波动最大处
    swings = []
    for a, b in zip(curve, curve[1:]):
        if a["scoreLead_white"] is None or b["scoreLead_white"] is None:
            continue
        swings.append({"from": a["move"], "to": b["move"],
                       "delta": round(b["scoreLead_white"] - a["scoreLead_white"], 1),
                       "score": b["scoreLead_white"]})
    swings.sort(key=lambda x: abs(x["delta"]), reverse=True)
    out = {"curve": curve, "biggest_swings": swings[:8]}
    with open(os.path.join(session, "eval_curve.json"), "w", encoding="utf-8") as f:
        f.write(json.dumps(out, ensure_ascii=False, indent=1))
    print("\n波动最大的区段(白目差变化):")
    for s in swings[:8]:
        print("  第%3d→%3d 手: %+.1f 目 (到第%d手白%s%.1f)" % (
            s["from"], s["to"], s["delta"], s["to"], "+" if s["score"] >= 0 else "", s["score"]))
    p.kill()


if __name__ == "__main__":
    main()