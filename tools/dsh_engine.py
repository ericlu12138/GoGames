# -*- coding: utf-8 -*-
"""DSH 人类桥:一个文件驱动的 GTP 引擎。
Sabaki 用 python.exe -u dsh_engine.py 启动它,就可以把"我(DSH)"当成对手。
- genmove 时:等待 D:\\Go\\my_move.txt 出现着法(我在对话里写入),拿到就返回
- 记录全部 GTP 通信与着法到 game_log.txt / game_state.json
- 轮到"我"时创建 waiting.flag,外部看门狗据此通知我
"""
import sys, os, time, json, re

BASE = r"D:\Go"
MY_MOVE = os.path.join(BASE, "my_move.txt")
LOG = os.path.join(BASE, "game_log.txt")
STATE = os.path.join(BASE, "game_state.json")
FLAG = os.path.join(BASE, "waiting.flag")

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stdin.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

moves = []          # [(color, move), ...]


def log(s):
    try:
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(s + "\n")
    except Exception:
        pass


def save_state():
    try:
        with open(STATE, "w", encoding="utf-8") as f:
            json.dump(moves, f, ensure_ascii=False)
    except Exception:
        pass


def respond(s=""):
    sys.stdout.write("= " + s + "\n\n")
    sys.stdout.flush()


def main():
    log("=== engine start %s ===" % time.strftime("%Y-%m-%d %H:%M:%S"))
    while True:
        line = sys.stdin.readline()
        if not line:
            log("=== stdin closed, exit ===")
            break
        cmd = line.strip()
        if not cmd:
            continue
        log("CMD " + cmd)
        parts = cmd.split()
        op = parts[0].lower()

        if op == "genmove":
            color = parts[1].lower() if len(parts) > 1 else "b"
            # 通知外部:轮到 DSH 了
            try:
                with open(FLAG, "w", encoding="utf-8") as f:
                    f.write(color)
            except Exception:
                pass
            log("WAITING_FOR_DSH color=%s" % color)
            mv = None
            for _ in range(1800):          # 最多等 30 分钟
                if os.path.exists(MY_MOVE):
                    try:
                        txt = open(MY_MOVE, encoding="utf-8-sig").read().strip()
                    except Exception:
                        txt = ""
                    if txt:
                        # 只取形如 Q16 / D4 / pass 的着法,去掉 BOM/空白/注释
                        mm = re.search(r'\b(pass|[A-Ta-t]\s*\d{1,2})\b', txt)
                        if mm:
                            mv = mm.group(1).replace(" ", "").upper()
                            try:
                                os.remove(MY_MOVE)
                            except Exception:
                                pass
                            break
                time.sleep(1)
            try:
                if os.path.exists(FLAG):
                    os.remove(FLAG)
            except Exception:
                pass
            if not mv:
                mv = "pass"
            moves.append([color, mv])
            save_state()
            log("GENMOVE %s -> %s" % (color, mv))
            respond(mv)

        elif op == "play":
            if len(parts) >= 3:
                moves.append([parts[1].lower(), parts[2]])
                save_state()
                log("PLAY %s %s" % (parts[1].lower(), parts[2]))
            respond()

        elif op == "clear_board":
            moves.clear()
            save_state()
            respond()

        elif op == "name":
            respond("DSH-Bridge")

        elif op == "list_commands":
            respond("protocol_version name version known_command list_commands quit "
                    "boardsize clear_board komi play genmove undo time_settings "
                    "time_left final_score showboard")

        elif op == "protocol_version":
            respond("2")

        elif op == "known_command":
            known = {"protocol_version","name","version","known_command","list_commands","quit",
                     "boardsize","clear_board","komi","play","genmove","undo","time_settings",
                     "time_left","final_score","showboard"}
            respond("true" if (len(parts) > 1 and parts[1] in known) else "false")

        elif op == "undo":
            if moves:
                moves.pop()
                save_state()
            respond()

        elif op in ("showboard", "time_settings", "time_left", "final_score"):
            respond()

        elif op == "version":
            respond("1.0")

        elif op == "quit":
            respond()
            log("=== quit ===")
            break

        else:
            respond()


if __name__ == "__main__":
    main()
