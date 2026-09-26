# -*- coding: utf-8 -*-
"""长会话对局引擎:一个 KataGo 进程跑完整局,DeepSeek 通过文件接口出招。

启动(后台):
  python -u play19.py --session F:\\围棋\\games\\g20260921b --my-color w --max-time 15

交互文件(都在 session 目录):
  my_move.txt  <- 我写(单个坐标,如 Q16;pass 表示停一手)
  state.json   -> 本程序写:当前手数/轮到谁/盘面,我读它来决定下一手
  log.txt      -> 全程 GTP 记录
"""
import argparse, json, os, re, subprocess, sys, time

KG = r"F:\围棋\KataGo-opencl"
LETTERS = "ABCDEFGHJKLMNOPQRST"


def board_text(moves, size=19):
    g = [["." for _ in range(size)] for _ in range(size)]
    for mv in moves:
        c = mv["coord"].upper()
        if c in ("PASS", "RESIGN") or c[0] not in LETTERS[:size]:
            continue
        x = LETTERS.index(c[0]); y = int(c[1:]) - 1
        if 0 <= x < size and 0 <= y < size:
            g[y][x] = "X" if mv["color"].lower() == "b" else "O"
    out = ["     " + " ".join(LETTERS[:size])]
    for y in range(size - 1, -1, -1):
        out.append("%3d  %s" % (y + 1, " ".join(g[y])))
    return "\n".join(out)


class Engine(object):
    def __init__(self, log):
        self.logf = open(log, "a", encoding="utf-8")
        self.p = subprocess.Popen(
            [os.path.join(KG, "katago.exe"), "gtp",
             "-model", os.path.join(KG, "kata1-tf3-b11c768-s11500M-d6163M.bin.gz"),
             "-config", os.path.join(KG, "gtp_play.cfg")],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            cwd=KG, universal_newlines=True, encoding="utf-8", errors="replace", bufsize=1)

    def cmd(self, c):
        self.logf.write(">>> " + c + "\n"); self.logf.flush()
        self.p.stdin.write(c + "\n"); self.p.stdin.flush()
        lines = []
        while True:
            ln = self.p.stdout.readline()
            if not ln:
                raise RuntimeError("引擎退出: " + c)
            s = ln.rstrip("\r\n")
            if s.strip() == "":
                break
            lines.append(s)
        ok = bool(lines) and lines[0].startswith("=")
        body = [(s[1:].strip() if i == 0 and s.startswith("=") else s) for i, s in enumerate(lines)]
        resp = "\n".join(body).strip()
        self.logf.write("<<< " + resp + "\n"); self.logf.flush()
        if not ok:
            raise RuntimeError(resp)
        return resp

    def close(self):
        try:
            self.cmd("quit")
        except Exception:
            pass
        try:
            self.p.wait(timeout=5)
        except Exception:
            self.p.kill()


def parse_move(resp):
    m = re.search(r"\b(pass|resign|[A-Ta-t]\d{1,2})\b", resp.strip())
    return m.group(1).upper() if m else "PASS"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--session", required=True)
    ap.add_argument("--my-color", default="w")
    ap.add_argument("--size", type=int, default=19)
    ap.add_argument("--komi", type=float, default=7.5)
    ap.add_argument("--max-time", type=float, default=15.0)
    ap.add_argument("--wait-sec", type=int, default=3600)
    a = ap.parse_args()

    sdir = a.session
    for d in (sdir, os.path.join(sdir, "logs")):
        if not os.path.isdir(d):
            os.makedirs(d)
    MINE = os.path.join(sdir, "my_move.txt")
    STATE = os.path.join(sdir, "state.json")
    errf = open(os.path.join(sdir, "log.txt"), "a", encoding="utf-8")
    my = a.my_color.lower()
    opp = "b" if my == "w" else "w"
    moves = []

    def write_state(extra=None, note=""):
        st = {
            "moves": len(moves),
            "side_to_move": "b" if len(moves) % 2 == 0 else "w",
            "my_color": my,
            "my_turn": (("b" if len(moves) % 2 == 0 else "w") == my),
            "game_over": False,
            "note": note,
            "board": board_text(moves, a.size),
            "history": ",".join("%s%s" % (m["color"].upper(), m["coord"]) for m in moves),
            "updated": time.strftime("%H:%M:%S"),
        }
        if extra:
            st.update(extra)
        tmp = STATE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(json.dumps(st, ensure_ascii=False, indent=1))
        os.replace(tmp, STATE)

    eng = Engine(os.path.join(sdir, "logs", "gtp.log"))
    try:
        eng.cmd("boardsize %d" % a.size)
        eng.cmd("komi %g" % a.komi)
        eng.cmd("kata-set-param maxTime %g" % a.max_time)
        eng.cmd("kata-set-param maxVisits 100000")
        eng.cmd("kata-set-param lagBuffer 1.0")
        eng.cmd("kata-set-param ponderingEnabled false")
        write_state(note="引擎就绪")

        passes = 0
        while passes < 2 and len(moves) < 500:
            side = "b" if len(moves) % 2 == 0 else "w"
            if side == opp:
                t0 = time.time()
                mv = parse_move(eng.cmd("genmove %s" % opp))
                sec = round(time.time() - t0, 1)
                moves.append({"color": opp, "coord": mv, "by": "katago", "sec": sec})
                passes = passes + 1 if mv == "PASS" else 0
                write_state(note="引擎已下 %s (%ss)" % (mv, sec))
                continue

            # 我这一手:等 my_move.txt
            write_state(note="轮到 DSH 出招")
            if os.path.exists(MINE):
                try:
                    os.remove(MINE)
                except Exception:
                    pass
            mv = None
            t0 = time.time()
            while time.time() - t0 < a.wait_sec:
                if os.path.exists(MINE):
                    try:
                        txt = open(MINE, encoding="utf-8-sig").read().strip()
                    except Exception:
                        txt = ""
                    mm = re.search(r"\b(pass|resign|[A-Ta-t]\d{1,2})\b", txt)
                    if mm:
                        mv = mm.group(1).upper()
                        break
                time.sleep(0.4)
            if not mv:
                errf.write("等待 DSH 着法超时\n"); errf.flush()
                break
            try:
                eng.cmd("play %s %s" % (my, mv))
            except RuntimeError as e:
                try:
                    os.remove(MINE)
                except Exception:
                    pass
                errf.write("我的着法 %s 非法: %s\n" % (mv, e)); errf.flush()
                write_state(note="着法 %s 非法,请换一个点" % mv)
                continue
            moves.append({"color": my, "coord": mv, "by": "deepseek"})
            passes = passes + 1 if mv == "PASS" else 0
            write_state(note="我已下 %s" % mv)

        # 终局
        try:
            fs = eng.cmd("final_score")
        except Exception as e:
            fs = "err: %s" % e
        write_state({"game_over": True, "final_score": fs, "note": "对局结束"},
                    note="对局结束")
        with open(os.path.join(sdir, "moves.json"), "w", encoding="utf-8") as f:
            f.write(json.dumps({"size": a.size, "komi": a.komi, "my_color": my,
                                "engine_color": opp, "moves": moves,
                                "final_score": fs}, ensure_ascii=False, indent=1))
        with open(os.path.join(sdir, "moves.txt"), "w", encoding="utf-8") as f:
            for i, m in enumerate(moves, 1):
                f.write("%3d  %s %-5s %s\n" % (i, m["color"].upper(), m["coord"], m.get("by", "")))
        print("GAME OVER moves=%d final_score=%s" % (len(moves), fs))
    finally:
        eng.close()
        errf.close()


if __name__ == "__main__":
    main()