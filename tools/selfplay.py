# -*- coding: utf-8 -*-
"""KataGo 自战:两个引擎进程互下,可设最高强度。

用法: python -u selfplay.py --session <目录> --max-time 12 [--no-noise] [--threads 16]

强度相关(全部经 kata-set-param 实测可用):
  maxTime / maxVisits 100000 / numSearchThreads / rootNoiseEnabled=false /
  chosenMoveTemperature=0 / chosenMoveTemperatureEarly=0 / analysisWideRootNoise=0
"""
import argparse, json, os, re, subprocess, sys, time

KG = r"F:\围棋\KataGo-opencl"
NET = "kata1-tf3-b11c768-s11500M-d6163M.bin.gz"
CFG = "gtp_play.cfg"
LETTERS = "ABCDEFGHJKLMNOPQRST"


class Engine(object):
    def __init__(self, name, log):
        self.name = name
        self.logf = open(log, "a", encoding="utf-8")
        self.p = subprocess.Popen(
            [os.path.join(KG, "katago.exe"), "gtp", "-model", os.path.join(KG, NET),
             "-config", os.path.join(KG, CFG)],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            cwd=KG, universal_newlines=True, encoding="utf-8", errors="replace", bufsize=1)

    def cmd(self, c, timeout=180):
        self.logf.write("[%s] >>> %s\n" % (self.name, c)); self.logf.flush()
        self.p.stdin.write(c + "\n"); self.p.stdin.flush()
        lines = []
        t0 = time.time()
        while True:
            ln = self.p.stdout.readline()
            if not ln:
                raise RuntimeError("%s 退出(命令 %s)" % (self.name, c))
            s = ln.rstrip("\r\n")
            if s.strip() == "":
                break
            lines.append(s)
            if time.time() - t0 > timeout:
                raise RuntimeError("%s 超时(命令 %s)" % (self.name, c))
        ok = bool(lines) and lines[0].startswith("=")
        body = [(s[1:].strip() if i == 0 and s.startswith("=") else s) for i, s in enumerate(lines)]
        resp = "\n".join(body).strip()
        self.logf.write("[%s] <<< %s\n" % (self.name, resp)); self.logf.flush()
        if not ok:
            raise RuntimeError("%s 报错: %s" % (self.name, resp))
        return resp

    def close(self):
        try:
            self.cmd("quit", timeout=20)
        except Exception:
            pass
        try:
            self.p.wait(timeout=5)
        except Exception:
            self.p.kill()
        try:
            self.logf.close()
        except Exception:
            pass


def parse_move(resp):
    m = re.search(r"\b(pass|resign|[A-Ta-t]\d{1,2})\b", resp.strip())
    return m.group(1).upper() if m else "PASS"


def board_text(moves, size=19):
    g = [["." for _ in range(size)] for _ in range(size)]
    for mv in moves:
        c = mv["coord"].upper()
        if c in ("PASS", "RESIGN") or c[0] not in LETTERS[:size]:
            continue
        x = LETTERS.index(c[0]); y = int(c[1:]) - 1
        if 0 <= x < size and 0 <= y < size:
            g[y][x] = "X" if mv["color"] == "b" else "O"
    out = ["     " + " ".join(LETTERS[:size])]
    for y in range(size - 1, -1, -1):
        out.append("%3d  %s" % (y + 1, " ".join(g[y])))
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--session", required=True)
    ap.add_argument("--size", type=int, default=19)
    ap.add_argument("--komi", type=float, default=7.5)
    ap.add_argument("--max-time", type=float, default=12.0)
    ap.add_argument("--max-visits", type=int, default=100000)
    ap.add_argument("--threads", type=int, default=16)
    ap.add_argument("--no-noise", action="store_true", help="关闭开局随机化(纯最强)")
    ap.add_argument("--limit", type=int, default=600)
    a = ap.parse_args()

    sdir = a.session
    for d in (sdir, os.path.join(sdir, "logs")):
        if not os.path.isdir(d):
            os.makedirs(d)
    log = os.path.join(sdir, "logs", "gtp.log")
    params = [("maxTime", a.max_time), ("maxVisits", a.max_visits),
              ("numSearchThreads", a.threads), ("lagBuffer", 1.0),
              ("ponderingEnabled", "false")]
    if a.no_noise:
        params += [("rootNoiseEnabled", "false"), ("chosenMoveTemperature", 0),
                   ("chosenMoveTemperatureEarly", 0), ("analysisWideRootNoise", 0)]

    e1 = Engine("B", log)   # 黑
    e2 = Engine("W", log)   # 白
    moves = []
    try:
        for e in (e1, e2):
            e.cmd("boardsize %d" % a.size)
            e.cmd("komi %g" % a.komi)
            for k, v in params:
                e.cmd("kata-set-param %s %s" % (k, v))
        passes = 0
        while passes < 2 and len(moves) < a.limit:
            color = "b" if len(moves) % 2 == 0 else "w"
            cur = e1 if color == "b" else e2
            t0 = time.time()
            mv = parse_move(cur.cmd("genmove %s" % color))
            sec = round(time.time() - t0, 1)
            moves.append({"color": color, "coord": mv, "sec": sec})
            passes = passes + 1 if mv == "PASS" else 0
            print("%3d  %s %-5s %4.1fs" % (len(moves), color.upper(), mv, sec), flush=True)
            (e2 if color == "b" else e1).cmd("play %s %s" % (color, mv))

        fs = ""
        try:
            fs = e1.cmd("final_score")
        except Exception as ex:
            fs = "err %s" % ex
        data = {"size": a.size, "komi": a.komi, "max_time": a.max_time,
                "max_visits": a.max_visits, "threads": a.threads,
                "no_noise": a.no_noise, "strength_params": {k: str(v) for k, v in params},
                "moves": moves, "final_score": fs, "mode": "katago-selfplay-max",
                "ended": time.strftime("%Y-%m-%d %H:%M:%S")}
        with open(os.path.join(sdir, "moves.json"), "w", encoding="utf-8") as f:
            f.write(json.dumps(data, ensure_ascii=False, indent=1))
        with open(os.path.join(sdir, "moves.txt"), "w", encoding="utf-8") as f:
            for i, m in enumerate(moves, 1):
                f.write("%3d  %s %-5s %4.1fs\n" % (i, m["color"].upper(), m["coord"], m["sec"]))
        with open(os.path.join(sdir, "final_board.txt"), "w", encoding="utf-8") as f:
            f.write(board_text(moves, a.size))
        print("GAME OVER moves=%d final_score=%s" % (len(moves), fs))
    finally:
        e1.close(); e2.close()


if __name__ == "__main__":
    main()