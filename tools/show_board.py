# -*- coding: utf-8 -*-
import json, sys
L = "ABCDEFGHJKLMNOPQRST"
d = json.load(open(r"F:\围棋\games\g20260921\moves.json", encoding="utf-8"))
g = [["." for _ in range(19)] for _ in range(19)]
for mv in d["moves"]:
    c = mv["coord"].upper()
    if c in ("PASS", "RESIGN"):
        continue
    x = L.index(c[0]); y = int(c[1:]) - 1
    g[y][x] = "X" if mv["color"] == "b" else "O"
print("手数:", len(d["moves"]), " 轮到:", "白(我)" if len(d["moves"]) % 2 == 1 else "黑")
print("     " + " ".join(L))
for y in range(18, -1, -1):
    print("%3d  %s" % (y + 1, " ".join(g[y])))
occ = {}
for mv in d["moves"]:
    occ.setdefault(mv["coord"].upper(), []).append(mv["color"])
print("\n最后 6 手:", ", ".join("%s%s" % (m["color"].upper(), m["coord"]) for m in d["moves"][-6:]))