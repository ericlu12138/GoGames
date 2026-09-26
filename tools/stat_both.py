# -*- coding: utf-8 -*-
import json, os, statistics
for name in ("maxsp_g1", "maxsp_g2"):
    S = os.path.join(r"F:\围棋\games", name)
    d = json.load(open(os.path.join(S, "moves.json"), encoding="utf-8"))
    mv = d["moves"]
    stones = [m for m in mv if m["coord"].upper() != "PASS"]
    passes = len(mv) - len(stones)
    secs = [m["sec"] for m in mv if m.get("sec")]
    print("%s: 总 %d 手(落子 %d,pass %d) 结果 %s | 平均 %.1fs/手" % (
        name, len(mv), len(stones), passes, d.get("final_score", "?"),
        statistics.mean(secs) if secs else 0))