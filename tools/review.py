# -*- coding: utf-8 -*-
"""复盘:重放棋谱 -> 终局数子 -> 引擎逐手评估找出败着"""
import importlib.util, os, sys, re

SGF = sys.argv[1] if len(sys.argv) > 1 else r"F:\围棋\games\godogo_20260913_175413.sgf"
SECS = float(sys.argv[2]) if len(sys.argv) > 2 else 1.0

spec = importlib.util.spec_from_file_location("gd", r"F:\围棋\GoDojo.py")
gd = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gd)

txt = open(SGF, encoding="utf-8").read()
size = int(re.search(r"SZ\[(\d+)\]", txt).group(1))
komi = float(re.search(r"KM\[([\d.]+)\]", txt).group(1))
raw = re.findall(r";([BW])\[([a-z]{2})\]", txt)
L2C = "ABCDEFGHJKLMNOPQRST"
moves = []
for (c, sgf) in raw:
    i = ord(sgf[0]) - 97
    j = ord(sgf[1]) - 97
    moves.append((c, L2C[i] + str(size - j)))
print("棋谱: %s" % os.path.basename(SGF))
print("棋盘 %d 路, 贴目 %.1f, 共 %d 手\n" % (size, komi, len(moves)))

b = gd.Board(size)
seq = []
caps = {"B": 0, "W": 0}
for k, (c, mv) in enumerate(moves):
    i = L2C.index(mv[0]); j = size - int(mv[1:])
    ok, cap, err = b.try_play(c, i, j)
    if not ok:
        print("  !! 第%d手 %s %s 非法(%s)" % (k + 1, c, mv, err))
        seq.append((c, mv, False, 0))
        continue
    caps[c] += len(cap)
    b.moves.append((c, i, j))
    seq.append((c, mv, True, len(cap)))

print("提子统计: 黑提 %d 子, 白提 %d 子" % (caps["B"], caps["W"]))
print("   " + " ".join(L2C[:size]))
for j in range(size):
    print("%2d %s" % (size - j, " ".join(b.g[i][j] for i in range(size))))
print()


def territory(grid, size):
    seen = [[False] * size for _ in range(size)]
    terr = {"B": 0, "W": 0, "N": 0}
    for j in range(size):
        for i in range(size):
            if grid[i][j] != "." or seen[i][j]:
                continue
            stack = [(i, j)]; seen[i][j] = True
            region, border = [], set()
            while stack:
                x, y = stack.pop(); region.append((x, y))
                for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    a, bb = x + dx, y + dy
                    if 0 <= a < size and 0 <= bb < size:
                        if grid[a][bb] == "." and not seen[a][bb]:
                            seen[a][bb] = True; stack.append((a, bb))
                        elif grid[a][bb] != ".":
                            border.add(grid[a][bb])
            if len(border) == 1:
                terr[border.pop()] += len(region)
            else:
                terr["N"] += len(region)
    return terr


terr = territory(b.g, size)
sb = sum(r.count("B") for r in b.g); sw = sum(r.count("W") for r in b.g)
black_score = sb + terr["B"]
white_score = sw + terr["W"] + komi
print("=== 终局数子(中国规则) ===")
print("你(黑): %d 子 + %d 目地 = %.1f" % (sb, terr["B"], black_score))
print("AI(白): %d 子 + %d 目地 + %.1f 贴目 = %.1f" % (sw, terr["W"], komi, white_score))
print("结果: %s %.1f 目" % ("白胜" if white_score > black_score else "黑胜",
                          abs(white_score - black_score)))
print()

print("=== 引擎逐手评估(找败着)===")
e = gd.Engine()
e.setup(size, komi)
prev_black_lead = None
rows = []
for k, (c, mv, ok, ncap) in enumerate(seq):
    if not ok:
        continue
    if not e.play(c, mv):
        e.resync([(cc, mm) for (cc, mm, o2, _n) in seq[:k + 1] if o2])
    nxt = "W" if c == "B" else "B"
    info = e.analyze(nxt, secs=SECS, maxmoves=3)
    if not info or info.get("scoreLead") is None:
        continue
    lead = info["scoreLead"] if nxt == "B" else -info["scoreLead"]
    alts = ",".join(x["move"] for x in (info.get("cands") or [])[:3])
    drop = (lead - prev_black_lead) if (c == "B" and prev_black_lead is not None) else 0.0
    rows.append((k + 1, c, mv, lead, alts, drop))
    prev_black_lead = lead

black_rows = sorted([r for r in rows if r[1] == "B"], key=lambda r: r[5])
print("你(黑)损失最大的 6 手:")
for (n, c, mv, lead, alts, drop) in black_rows[:6]:
    print("  第%3d手 %-4s 下完后黑领先 %+6.1f 目   掉 %.1f 目   引擎推荐: %s"
          % (n, mv, lead, -drop, alts))
print()
print("最后 10 手形势(黑领先目数):")
for r in rows[-10:]:
    print("  第%3d手 %s %-4s -> 黑 %+6.1f 目" % (r[0], r[1], r[2], r[3]))
