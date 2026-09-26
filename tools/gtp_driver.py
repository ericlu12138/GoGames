# -*- coding: utf-8 -*-
"""19 路对局驱动：DeepSeek(白) vs KataGo(黑)，GTP 长会话，限时 20 秒/手。

每回合调用一次(加 -u 无缓冲):
  python -u gtp_driver.py --session F:\围棋\games\g20260921 --me-move Q16

对局中只向引擎要 genmove(对手应手),不读引擎推荐点 —— 我的每一手都自己算。
形势判断与候选点留到赛后 review19.py 一次算清。
"""
import argparse, json, os, re, subprocess, sys, time

KG_DIR = r"F:\围棋\KataGo-opencl"
LETTERS = "ABCDEFGHJKLMNOPQRST"


class Engine(object):
    def __init__(self, log_path, cfg="gtp_play.cfg", model="kata1-tf3-b11c768-s11500M-d6163M.bin.gz"):
        self.kg = KG_DIR
        self.logf = open(log_path, "a", encoding="utf-8") if log_path else None
        errp = (log_path + ".stderr") if log_path else os.devnull
        self.errf = open(errp, "a", encoding="utf-8")
        self.p = subprocess.Popen(
            [os.path.join(self.kg, "katago.exe"), "gtp",
             "-model", os.path.join(self.kg, model),
             "-config", os.path.join(self.kg, cfg)],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=self.errf,
            cwd=self.kg, universal_newlines=True, encoding="utf-8",
            errors="replace", bufsize=1)

    def _log(self, s):
        if self.logf:
            self.logf.write(s.rstrip() + "\n")
            self.logf.flush()

    def cmd(self, c):
        self._log(">>> " + c)
        self.p.stdin.write(c + "\n")
        self.p.stdin.flush()
        lines = []
        while True:
            line = self.p.stdout.readline()
            if not line:
                raise RuntimeError("katago 退出(命令 %r 无应答)" % c)
            s = line.rstrip("\r\n")
            if s.strip() == "":
                break
            lines.append(s)
        ok = bool(lines) and lines[0].startswith("=")
        body = []
        for i, s in enumerate(lines):
            if i == 0 and s.startswith("="):
                body.append(s[1:].strip())
            else:
                body.append(s)
        resp = "\n".join(body).strip()
        self._log("<<< " + resp)
        if not ok:
            raise RuntimeError("katago 报错: %s" % resp)
        return resp

    def close(self):
        try:
            self.cmd("quit")
        except Exception:
            pass
        try:
            self.p.wait(timeout=8)
        except Exception:
            self.p.kill()
        for f in (self.logf, self.errf):
            try:
                if f:
                    f.close()
            except Exception:
                pass


def parse_move(resp):
    m = re.search(r"\b(pass|resign|[A-Ta-t]\d{1,2})\b", resp.strip())
    return m.group(1).upper() if m else "PASS"


def board_text(moves, size=19):
    g = [["." for _ in range(size)] for _ in range(size)]
    for mv in moves:
        c = mv["coord"].upper()
        if c in ("PASS", "RESIGN"):
            continue
        if c[0] not in LETTERS[:size]:
            continue
        x = LETTERS.index(c[0])
        y = int(c[1:]) - 1
        if 0 <= x < size and 0 <= y < size:
            g[y][x] = "X" if mv["color"].lower() == "b" else "O"
    out = ["     " + " ".join(LETTERS[:size])]
    for y in range(size - 1, -1, -1):
        out.append("%3d  %s" % (y + 1, " ".join(g[y])))
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--session", required=True)
    ap.add_argument("--me-move", default=None)
    ap.add_argument("--my-color", default="w")
    ap.add_argument("--size", type=int, default=19)
    ap.add_argument("--komi", type=float, default=7.5)
    ap.add_argument("--max-time", type=float, default=20.0)
    ap.add_argument("--max-visits", type=int, default=100000)
    ap.add_argument("--pass", dest="do_pass", action="store_true")
    ap.add_argument("--final", action="store_true", help="终局数子")
    a = ap.parse_args()

    sdir = a.session
    logs = os.path.join(sdir, "logs")
    for d in (sdir, logs):
        if not os.path.isdir(d):
            os.makedirs(d)
    mj = os.path.join(sdir, "moves.json")

    if os.path.exists(mj):
        with open(mj, encoding="utf-8") as f:
            data = json.load(f)
    else:
        data = {"size": a.size, "komi": a.komi, "my_color": a.my_color.lower(),
                "engine_color": "b" if a.my_color.lower() == "w" else "w",
                "max_time": a.max_time, "moves": [],
                "started": time.strftime("%Y-%m-%d %H:%M:%S")}
    moves = data["moves"]
    my, opp = data["my_color"], data["engine_color"]

    def stm():
        return "b" if len(moves) % 2 == 0 else "w"

    def passes_tail():
        n = 0
        for m in reversed(moves):
            if m["coord"].upper() == "PASS":
                n += 1
            else:
                break
        return n

    if a.me_move and stm() != my:
        print(json.dumps({"ok": False, "error": "不是我的回合,轮到 %s" % stm()}, ensure_ascii=False))
        return
    if a.do_pass and stm() != my:
        print(json.dumps({"ok": False, "error": "不是我的回合,轮到 %s" % stm()}, ensure_ascii=False))
        return

    eng = Engine(os.path.join(logs, "gtp.log"))
    res = {"ok": True}
    try:
        eng.cmd("boardsize %d" % a.size)
        eng.cmd("komi %g" % a.komi)
        eng.cmd("kata-set-param maxTime %g" % a.max_time)
        eng.cmd("kata-set-param maxVisits %d" % a.max_visits)
        eng.cmd("kata-set-param lagBuffer 1.0")
        eng.cmd("kata-set-param ponderingEnabled false")
        for mv in moves:
            eng.cmd("play %s %s" % (mv["color"], mv["coord"]))

        if a.do_pass or a.me_move:
            mv = "PASS" if a.do_pass else a.me_move.strip().upper()
            eng.cmd("play %s %s" % (my, mv))
            moves.append({"color": my, "coord": mv, "by": "deepseek",
                          "t": time.strftime("%H:%M:%S")})
            res["my_move"] = mv

        over = passes_tail() >= 2
        if not over and stm() == opp:
            t0 = time.time()
            resp = eng.cmd("genmove %s" % opp)
            mv = parse_move(resp)
            res["engine_move"] = mv
            res["engine_sec"] = round(time.time() - t0, 1)
            moves.append({"color": opp, "coord": mv, "by": "katago",
                          "t": time.strftime("%H:%M:%S")})
            over = passes_tail() >= 2

        res["stm"] = stm()
        res["move_no"] = len(moves)
        res["game_over"] = over
        if a.final:
            res["final_score"] = eng.cmd("final_score")
    finally:
        eng.close()

    data["moves"] = moves
    data["updated"] = time.strftime("%Y-%m-%d %H:%M:%S")
    with open(mj, "w", encoding="utf-8") as f:
        f.write(json.dumps(data, ensure_ascii=False, indent=1))
    with open(os.path.join(sdir, "moves.txt"), "w", encoding="utf-8") as f:
        for i, mv in enumerate(moves, 1):
            f.write("%3d  %s %-5s %s\n" % (i, mv["color"].upper(), mv["coord"], mv.get("by", "")))
    res["moves"] = ",".join("%s%s" % (m["color"].upper(), m["coord"]) for m in moves)
    res["board"] = board_text(moves, a.size)
    print(json.dumps(res, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()