# -*- coding: utf-8 -*-
import json, re
h = open(r"F:\围棋\games\selfplay_19\viewer.html", encoding="utf-8").read()
print("文件大小:", len(h))
print("有 canvas:", "<canvas" in h, "| 有 MOVES 数据:", '"p"' in h)
m = re.search(r"const MOVES = (\[.*?\]);\n", h, re.S)
mv = json.loads(m.group(1)) if m else []
print("着法数:", len(mv), "| 首手:", mv[0] if mv else None, "| 末手:", mv[-1] if mv else None)
# 用同一套逻辑算出终局盘面,验证渲染逻辑
L = "ABCDEFGHJKLMNOPQRST"; N = 19
g = [["." for _ in range(N)] for _ in range(N)]
for k in mv:
    x = L.index(k["p"][0]); y = N - int(k["p"][1:])
    g[y][x] = "X" if k["c"] == "b" else "O"
print("     " + " ".join(L))
for r in range(N):
    print("%3d  %s" % (N - r, " ".join(g[r])))