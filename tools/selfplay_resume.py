# -*- coding: utf-8 -*-
"""续下被中断的自战:从 moves_partial.json 恢复,继续下到终局。
引擎崩溃时自动重启并重放局面(避免再丢棋谱)。

用法: python -u selfplay_resume.py --session <目录> --max-time 10
"""
import argparse, json, os, re, subprocess, sys, time

KG = r"F:\围棋\KataGo-opencl"
NET = "kata1-tf3-b11c768-s11500M-d6163M.bin.gz"
CFG = "gtp_play.cfg"
LETTERS = "ABCDEFGHJKLMNOPQRST"


class Engine(object):
    def __init__(self, name, log_path, params, size, komi):
        self.name = name; self.log_path = log_path
        self.params = params; self.size = size; self.komi = komi
        self.spawn()

    def spawn(self):
        self.logf = open(self.log_path, "a", encoding="utf-8")
        self.p = subprocess.Popen(
            [os.path.join(KG, "katago.exe"), "gtp", "-model", os.path.join(KG, NET),
             "-config", os.path.join(KG, CFG)],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            cwd=KG, universal_newlines=True, encoding="utf-8", errors="replace", bufsize=1)
        self.cmd("boardsize %d" % self.size)
        self.cmd("komi %g" % self.komi)
        for k, v in self.params:
            self.cmd("kata-set-param %s %s" % (k, v))

    def cmd(self, c, timeout=180):
        self.logf.write("[%s] >>> %s\n" % (self.name, c)); self.logf.flush()
        self.p.stdin.write(c + "\n"); self.p.stdin.flush()
        lines = []; t0 = time.time()
        while True:
            ln = self.p.stdout.readline()
            if not ln:
                raise RuntimeError("%s 进程结束" % self.name)
            s = ln.rstrip("\r\n")
            if s.strip() == "":
                break
            lines.append(s)
            if time.time() - t0 > timeout:
                raise RuntimeError("%s 超时" % self.name)
        ok = bool(lines) and lines[0].startswith("=")
        body = [(s[1:].strip() if i == 0 and s.startswith("=") else s) for i, s in enumerate(lines)]
        resp = "\n".join(body).strip()
        self.logf.write("[%s] <<< %s\n" % (self.name, resp)); self.logf.flush()
        if not ok:
            raise RuntimeError("%s 报错: %s" % (self.name, resp))
        return resp

    def kill(self):
        try: self.p.kill()
        except Exception: pass
        try: self.logf.close()
        except Exception: pass

    def restart(self, moves):
        """重启并把已下的着法全部重放回去。"""
        print("  !! %s 引擎异常,重启并重放 %d 手" % (self.name, len(moves)), flush=True)
        self.kill()
        self.spawn()
        for mv in moves:
            self.cmd("play %s %s" % (mv["color"], mv["coord"]))


def parse_move(resp):
    m = re.search(r"\b(pass|resign|[A-Ta-t]\d{1,2})\b", resp.strip())
    return m.group(1).upper() if m else "PASS"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--session", required=True)
    ap.add_argument("--max-time", type=float, default=10.0)
    ap.add_argument("--max-visits", type=int, default=100000)
    ap.add_argument("--threads", type=int, default=16)
    ap.add_argument("--limit", type=int, default=600)
    a = ap.parse_args()
    S = a.session
    log = os.path.join(S, "logs", "gtp_resume.log")
    src = os.path.join(S, "moves_partial.json")
    d = json.load(open(src, encoding="utf-8"))
    moves = d["moves"]
    print("恢复:已有 %d 手" % len(moves), flush=True)
    params = [("maxTime", a.max_time), ("maxVisits", a.max_visits),
              ("numSearchThreads", a.threads), ("lagBuffer", 1.0),
              ("ponderingEnabled", "false"), ("rootNoiseEnabled", "false"),
              ("chosenMoveTemperature", 0), ("chosenMoveTemperatureEarly", 0),
              ("analysisWideRootNoise", 0)]
    e = {"b": Engine("B", log, params, d["size"], d["komi"]),
         "w": Engine("W", log, params, d["size"], d["komi"])}
    for mv in moves:                      # 两个引擎都重放到当前局面
        e[mv["color"]].cmd("play %s %s" % (mv["color"], mv["coord"]))
        other = "w" if mv["color"] == "b" else "b"
        e[other].cmd("play %s %s" % (mv["color"], mv["coord"]))

    passes = 0
    while passes < 2 and len(moves) < a.limit:
        color = "b" if len(moves) % 2 == 0 else "w"
        other = "w" if color == "b" else "b"
        try:
            t0 = time.time()
            mv = parse_move(e[color].cmd("genmove %s" % color))
            sec = round(time.time() - t0, 1)
        except Exception as ex:
            print("  着法失败: %s" % ex, flush=True)
            e[color].restart(moves)
            continue
        moves.append({"color": color, "coord": mv, "sec": sec})
        passes = passes + 1 if mv == "PASS" else 0
        print("%3d  %s %-5s %4.1fs" % (len(moves), color.upper(), mv, sec), flush=True)
        try:
            e[other].cmd("play %s %s" % (color, mv))
        except Exception:
            e[other].restart(moves)
        # 每 20 手存一次盘,防再丢
        if len(moves) % 20 == 0:
            json.dump({"size": d["size"], "komi": d["komi"], "max_time": a.max_time,
                       "moves": moves, "mode": "katago-selfplay-max"},
                      open(os.path.join(S, "moves_partial.json"), "w", encoding="utf-8"),
                      ensure_ascii=False, indent=1)

    fs = ""
    try:
        fs = e["b"].cmd("final_score")
    except Exception as ex:
        fs = "err %s" % ex
    data = {"size": d["size"], "komi": d["komi"], "max_time": a.max_time,
            "max_visits": a.max_visits, "threads": a.threads, "no_noise": True,
            "mode": "katago-selfplay-max", "resumed": True, "moves": moves,
            "final_score": fs, "ended": time.strftime("%Y-%m-%d %H:%M:%S")}
    json.dump(data, open(os.path.join(S, "moves.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    with open(os.path.join(S, "moves.txt"), "w", encoding="utf-8") as f:
        for i, m in enumerate(moves, 1):
            f.write("%3d  %s %-5s %s\n" % (i, m["color"].upper(), m["coord"],
                                           ("%4.1fs" % m["sec"]) if m.get("sec") else "-"))
    e["b"].kill(); e["w"].kill()
    print("GAME OVER moves=%d final_score=%s" % (len(moves), fs))


if __name__ == "__main__":
    main()