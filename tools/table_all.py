# -*- coding: utf-8 -*-
import json, os
rows = []
for name, label in (("selfplay_19","5秒档(带随机)"), ("maxsp_g1","最强 第1局"),
                    ("maxsp_g2","最强 第2局"), ("g3","最强 第3局"), ("g4","最强 第4局")):
    S = os.path.join(r"F:\围棋\games", name)
    d = json.load(open(os.path.join(S, "moves.json"), encoding="utf-8"))
    v = open(os.path.join(S, "viewer.html"), encoding="utf-8").read()
    import re
    meta = json.loads(re.search(r"const META = (\{.*?\});", v, re.S).group(1))
    stones = len([m for m in d["moves"] if m["coord"].upper() != "PASS"])
    passes = len(d["moves"]) - stones
    from statistics import mean
    secs = [m["sec"] for m in d["moves"] if m.get("sec")]
    rows.append((label, stones, passes, d.get("final_score","?"), meta["cap_b"], meta["cap_w"],
                 meta["on_b"], meta["on_w"], meta["empty"],
                 round(mean(secs),1) if secs else "-"))
print("%-14s %5s %5s %9s %6s %6s %6s %6s %6s %7s" % (
    "局面","落子","pass","结果","黑被提","白被提","盘上黑","盘上白","空点","秒/手"))
for r in rows:
    print("%-14s %5d %5d %9s %6d %6d %6d %6d %6d %7s" % r)