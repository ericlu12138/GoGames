# -*- coding: utf-8 -*-
"""复盘 v2:重放棋谱 -> 终局数子 -> 用 genmove_analyze+undo 逐手评估"""
import importlib.util, os, sys, re

SGF = sys.argv[1] if len(sys.argv) > 1 else r"F:\围棋\games\godogo_20260913_175413.sgf"

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

b = gd.Board(size)
seq, caps = [], {"B": 0, "W": 0}
for k, (c, mv) in enumerate(moves):
    i = L2C.index(mv[0]); j = size - int(mv[1:])
    ok, cap, err = b.try_play(c, i, j)
    if not ok:
        seq.append((c, mv, False, 0)); continue
    caps[c] += len(cap); b.moves.append((c, i, j)); seq.append((c, mv, True, len(cap)))

print("棋谱 %s  |  %d 路  |  贴目 %.1f  |  %d 手" % (os.path.basename(SGF), size, komi, len(seq)))
print("提子: 黑提 %d 子, 白提 %d 子" % (caps["B"], caps["W"]))


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
print("终局盘面:")
print("   " + " ".join(L2C[:size]))
for j in range(size):
    print("%2d %s" % (size - j, " ".join(b.g[i][j] for i in range(size))))
print("终局数子(中国规则): 黑 %.1f  vs  白 %.1f  ->  %s %.1f 目" % (
    sb + terr["B"], sw + terr["W"] + komi,
    "白胜" if (sw + terr["W"] + komi) > (sb + terr["B"]) else "黑胜",
    abs((sw + terr["W"] + komi) - (sb + terr["B"]))))
print()

print("=== 逐手评估(每手:该走方的引擎最佳手与目差)===")
e = gd.Engine()
e.setup(size, komi)
rows = []
prev_lead_black = None
for k, (c, mv, ok, ncap) in enumerate(seq):
    if not ok:
        continue
    # 1) 评估"还没走这一手"的局面
    best, info = e.genmove_analyze(c, maxmoves=3, interval=60)
    if info and info.get("scoreLead") is not None:
        lead_before = info["scoreLead"] if c == "B" else -info["scoreLead"]
        alts = ",".join(x["move"] for x in (info.get("cands") or [])[:3])
    else:
        lead_before, alts = None, ""
    # 2) 撤掉引擎的试走,改成实战着法
    e.undo()
    if not e.play(c, mv):
        print("  第%d手 %s %s 引擎判非法 -> 从此处重新同步" % (k + 1, c, mv))
        e.resync([(cc, mm) for (cc, mm, o2, _n) in seq[:k + 1] if o2])
    drop = None
    if lead_before is not None and prev_lead_black is not None and c == "B":
        drop = lead_before - prev_lead_black
        rows.append((k + 1, c, mv, lead_before, drop, alts))
    prev_lead_black = None
    # 记录"轮到下一手前"的黑方目差:用下一轮的 lead_before 补
    if k + 1 < len(seq):
        nxt_c = seq[k + 1][0]
        if nxt_c == "W":
            # 白方视角的目差 = -(黑方目差),下一轮会给出
            pass

blk = sorted([r for r in rows if r[4] is not None], key=lambda r: r[4])
print("你(黑)目差下滑最多的 6 手:")
for (n, c, mv, lb, drop, alts) in blk[:6]:
    print("   第%3d手 %-4s  该走时最佳目差 %+6.1f,你走成 %+6.1f  (掉 %.1f)  推荐: %s"
          % (n, mv, lb, lb - drop, -drop, alts))
