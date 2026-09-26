# -*- coding: utf-8 -*-
"""用 state.json 的 history 生成 moves.json(认输收盘用)。"""
import json, os, re, sys
s = r"F:\围棋\games\g20260921b"
d = json.load(open(os.path.join(s, "state.json"), encoding="utf-8"))
h = [x for x in d["history"].split(",") if x]
moves = []
for i, x in enumerate(h, 1):
    color, coord = x[0].lower(), x[1:]
    if coord.upper() in ("PASS", "RESIGN"):
        continue
    moves.append({"color": color, "coord": coord, "by": "deepseek" if (color == "w") else "katago"})
out = {"size": 19, "komi": 7.5, "my_color": "w", "engine_color": "b",
       "moves": moves, "result": "W+resign", "aborted_at": len(moves)}
json.dump(out, open(os.path.join(s, "moves.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
with open(os.path.join(s, "moves.txt"), "w", encoding="utf-8") as f:
    for i, m in enumerate(moves, 1):
        f.write("%3d  %s %-5s %s\n" % (i, m["color"].upper(), m["coord"], m["by"]))
print("saved moves:", len(moves))
print(",".join("%s:%s" % (m["color"], m["coord"]) for m in moves))