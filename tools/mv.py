# -*- coding: utf-8 -*-
"""落一手并等待引擎应手,输出局面摘要。用法: python -u mv.py <session> <坐标>"""
import json, os, sys, time
s = sys.argv[1] if len(sys.argv) > 1 else r"F:\围棋\games\g20260921b"
mv = sys.argv[2]
st = os.path.join(s, "state.json")
cur = json.load(open(st, encoding="utf-8"))["moves"]
open(os.path.join(s, "my_move.txt"), "w", encoding="utf-8").write(mv + "\n")
t0 = time.time()
while time.time() - t0 < 120:
    time.sleep(0.7)
    d = json.load(open(st, encoding="utf-8"))
    if d["moves"] >= cur + 2 or d.get("game_over"):
        break
print("我:%s | 引擎:%s | 手数:%d | %s" % (mv, d.get("note", ""), d["moves"], d["updated"]))
h = d["history"].split(",") if d["history"] else []
print("最近6手:", ",".join(h[-6:]))
L = "ABCDEFGHJKLMNOPQRST"
g = [["." for _ in range(19)] for _ in range(19)]
for x in h:
    c, co = x[0], x[1:]
    if co in ("PASS", "RESIGN"): continue
    g[int(co[1:]) - 1][L.index(co[0])] = "X" if c == "B" else "O"
rows = ["     " + " ".join(L)]
for y in range(18, -1, -1):
    rows.append("%3d  %s" % (y + 1, " ".join(g[y])))
# 只打印有空点的行区间,减少输出
ys = [y for y in range(19) if any(ch != "." for ch in g[y])]
lo, hi = (min(ys) - 1, max(ys) + 1) if ys else (0, 18)
print("\n".join([rows[0]] + [rows[19 - y] for y in range(hi, lo - 1, -1)]))