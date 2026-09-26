# -*- coding: utf-8 -*-
"""对局形势评估:与 KataGo 建立 GTP 会话,重放全部着法,流式分析指定秒数。
用法: python -u review19.py <session目录> [秒数] [--cands]
注意: 只读取 scoreLead / winrate,不取推荐点(除非 --cands)。
"""
import json, os, re, subprocess, sys, threading, time

KG = r"F:\围棋\KataGo-opencl"
NET = os.path.join(KG, "kata1-tf3-b11c768-s11500M-d6163M.bin.gz")
CFG = os.path.join(KG, "gtp_play.cfg")


def num(pat, s):
    m = re.search(pat, s)
    return float(m.group(1)) if m else None


def main():
    session = sys.argv[1]
    budget = float(sys.argv[2]) if len(sys.argv) > 2 and not sys.argv[2].startswith("--") else 15.0
    want_cands = "--cands" in sys.argv
    d = json.load(open(os.path.join(session, "moves.json"), encoding="utf-8"))
    moves = [m for m in d["moves"] if m["coord"].upper() not in ("PASS", "RESIGN")]
    side = "b" if len(moves) % 2 == 0 else "w"

    p = subprocess.Popen([os.path.join(KG, "katago.exe"), "gtp", "-model", NET, "-config", CFG],
                         stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                         cwd=KG, universal_newlines=True, encoding="utf-8", errors="replace", bufsize=1)
    lines = []
    def reader():
        for ln in p.stdout:
            lines.append(ln.rstrip("\r\n"))
    th = threading.Thread(target=reader); th.daemon = True; th.start()

    def gtp(cmd):
        lines.clear()
        p.stdin.write(cmd + "\n"); p.stdin.flush()
        t0 = time.time()
        while time.time() - t0 < 90:
            if lines and lines[-1].strip() == "" and len(lines) > 1:
                break
            time.sleep(0.05)
        return " | ".join(x for x in lines if x.strip())

    gtp("boardsize %d" % d["size"])
    gtp("komi %g" % d["komi"])
    for m in moves:
        gtp("play %s %s" % (m["color"], m["coord"]))

    lines.clear()
    p.stdin.write("kata-analyze %s interval 200 maxmoves 8\n" % side)
    p.stdin.flush()
    t0 = time.time()
    best = ""
    while time.time() - t0 < budget:
        time.sleep(0.5)
        cand = [l for l in lines if l.startswith("info ") and "scoreLead" in l]
        if cand:
            best = cand[-1]
    p.kill()

    wr = num(r"\bwinrate ([0-9.]+)", best)
    sl = num(r"\bscoreLead (-?[0-9.]+)", best)
    pv = re.search(r"\bpv ((?:[A-T][0-9]{1,2} ?)+)", best)
    out = {
        "moves": len(moves),
        "side_to_move": side,
        "visits": num(r"\bvisits (\d+)", best),
        "winrate_white": round(wr if side == "w" else 1 - wr, 4) if wr is not None else None,
        "scoreLead_white": round(sl if side == "w" else -sl, 2) if sl is not None else None,
        "pv": pv.group(1).strip() if pv else None,
        "elapsed": round(time.time() - t0, 1),
    }
    if want_cands:
        cands = []
        for seg in best.split("info move ")[1:]:
            parts = seg.split()
            if not parts:
                continue
            w2 = num(r"\bwinrate ([0-9.]+)", seg)
            s2 = num(r"\bscoreLead (-?[0-9.]+)", seg)
            cands.append({"move": parts[0],
                          "winrate_white": round(w2 if side == "w" else 1 - w2, 4) if w2 is not None else None,
                          "scoreLead_white": round(s2 if side == "w" else -s2, 2) if s2 is not None else None})
        out["candidates"] = cands
    print(json.dumps(out, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()