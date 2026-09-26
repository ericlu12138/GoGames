# -*- coding: utf-8 -*-
import re, sys
L = "ABCDEFGHJKLMNOPQRST"
txt = open(r"F:\围棋\games\g20260921\final_moves.txt", encoding="utf-8").read() if len(sys.argv)<2 else open(sys.argv[1], encoding="utf-8").read()
g=[["." for _ in range(19)] for _ in range(19)]
n=0
for line in txt.splitlines():
    m = re.match(r"\s*(\d+)\s+([BW])\s+(\S+)", line)
    if not m: continue
    mv = m.group(3).upper()
    if mv in ("PASS","RESIGN"): continue
    x=L.index(mv[0]); y=int(mv[1:])-1
    g[y][x] = "X" if m.group(2)=="B" else "O"; n+=1
print("盘上子数:", n)
print("     " + " ".join(L))
for y in range(18,-1,-1):
    print("%3d  %s" % (y+1, " ".join(g[y])))