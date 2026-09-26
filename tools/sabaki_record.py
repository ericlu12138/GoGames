# -*- coding: utf-8 -*-
"""Sabaki 实时棋谱记录器 + 轮次哨兵
- 每 2 秒读一次盘,发现新落子就按交替顺序记进 SGF
- --once:发现对手落子后打印并退出(用于把我从"等待"中唤醒)
- 默认无限运行,持续记录
用法:
  python sabaki_record.py --size 19 --my-color b            # 持续记录
  python sabaki_record.py --size 19 --my-color b --once     # 等对手一手后退出
"""
import sys, os, time, json, datetime, argparse, importlib.util

LETTERS = "ABCDEFGHJKLMNOPQRST"
GAMES = r"D:\Go\games"
MOVES_JSON = r"D:\Go\game_moves.json"

spec = importlib.util.spec_from_file_location("bot", r"D:\Go\sabaki_bot.py")
bot = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bot)


def sgf_coord(i, j, size):
    """i=列索引(0起,左->右), j=行索引(0起,上->下)"""
    return chr(97 + i) + chr(97 + j)


def write_sgf(path, size, moves, komi=7.5):
    parts = ["(;GM[1]FF[4]CA[UTF-8]AP[Sabaki+DSH:1.0]SZ[%d]KM[%.1f]" % (size, komi)]
    parts.append("DT[%s]" % datetime.datetime.now().strftime("%Y-%m-%d"))
    for (color, i, j) in moves:
        parts.append(";%s[%s]" % (color.upper(), sgf_coord(i, j, size)))
    parts.append(")")
    with open(path, "w", encoding="utf-8") as f:
        f.write("".join(parts))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--size", type=int, default=0)      # 0=自动
    ap.add_argument("--my-color", default="b")
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--interval", type=float, default=2.0)
    ap.add_argument("--sgf", default="")
    ap.add_argument("--seed", default="", help="已下着法,逗号分隔(黑先交替),用于补齐历史")
    a = ap.parse_args()

    os.makedirs(GAMES, exist_ok=True)
    sgf_path = a.sgf or os.path.join(GAMES, "game_%s.sgf" % datetime.datetime.now().strftime("%Y%m%d_%H%M%S"))
    moves = []          # [(color, i, j)]  color: 'B'/'W'
    prev = None
    size = a.size
    seeded = False
    print("记录器启动 -> %s (我执 %s)" % (sgf_path, a.my_color), flush=True)

    while True:
        r = bot.read_board()
        if not r:
            time.sleep(a.interval)
            continue
        out = r[0]
        if not size:
            size = int(out["size"])
        if not seeded and a.seed and size:
            for k, tok in enumerate([t.strip() for t in a.seed.split(",") if t.strip()]):
                col = "B" if k % 2 == 0 else "W"
                letter = tok[0].upper()
                num = int(tok[1:])
                i = LETTERS.index(letter)
                j = size - num
                moves.append((col, i, j))
            seeded = True
            write_sgf(sgf_path, size, moves)
            print("已补齐历史 %d 手: %s" % (len(moves), a.seed), flush=True)
        cur = {(int(s[0]), int(s[1])): s[2] for s in out["stones"]}
        if prev is None:
            prev = cur
            if cur:
                # 已有子:按黑白交替尽可能推断(黑先)
                seq = []
                for (i, j), c in sorted(cur.items(), key=lambda kv: (kv[0][0], kv[0][1])):
                    seq.append((i, j, c))
                # 不写入历史(无法确定顺序),仅作为基线
                print("基线盘面 %d 子(历史未写入 SGF)" % len(cur), flush=True)
            else:
                print("空盘,开始记录", flush=True)
            write_sgf(sgf_path, size, moves)
            time.sleep(a.interval)
            continue

        added = [(k, v) for k, v in cur.items() if k not in prev]
        removed = [k for k in prev if k not in cur]
        if added or removed:
            for (k, c) in sorted(added, key=lambda kv: (kv[0][1], kv[0][0])):
                i, j = k
                moves.append((c, i, j))
                coord = LETTERS[i] + str(size - j)
                print("记录: %s %s%s" % (c, LETTERS[i], size - j), flush=True)
            if removed:
                print("（本步有 %d 子被提)" % len(removed), flush=True)
            write_sgf(sgf_path, size, moves)
            with open(MOVES_JSON, "w", encoding="utf-8") as f:
                json.dump({"size": size, "sgf": sgf_path,
                           "moves": [{"color": c, "coord": LETTERS[i] + str(size - j)} for (c, i, j) in moves]},
                          f, ensure_ascii=False, indent=1)
            prev = cur
            if a.once:
                print("== 对手已落子,退出哨兵 ==", flush=True)
                break
        else:
            prev = cur
        time.sleep(a.interval)


if __name__ == "__main__":
    main()
