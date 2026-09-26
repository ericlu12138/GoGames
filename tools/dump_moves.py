# -*- coding: utf-8 -*-
import json, os
L="ABCDEFGHJKLMNOPQRST"
d=json.load(open(r"F:\围棋\games\g20260921\moves.json",encoding="utf-8"))
mv=[(m["color"],m["coord"],m.get("by","")) for m in d["moves"] if m["coord"].upper() not in ("PASS","RESIGN")]
parts=[]
for i,(c,co,by) in enumerate(mv,1):
    parts.append("%s:%s"%(c,co))
print(",".join(parts))
print("MOUSE", len(mv))