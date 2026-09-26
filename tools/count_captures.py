# -*- coding: utf-8 -*-
"""统计自战里的提子情况和盘面密度。"""
import json, os
L = "ABCDEFGHJKLMNOPQRST"

def neighbors(x, y, N=19):
    for dx, dy in ((1,0),(-1,0),(0,1),(0,-1)):
        nx, ny = x+dx, y+dy
        if 0 <= nx < N and 0 <= ny < N:
            yield nx, ny

def analyze(path):
    d = json.load(open(path, encoding="utf-8"))
    b = {}
    capB = capW = 0   # 黑被提 / 白被提
    events = []
    n = 0
    for m in d["moves"]:
        c = m["coord"].upper()
        if c in ("PASS", "RESIGN"):
            continue
        color = m["color"]
        x, y = L.index(c[0]), int(c[1:]) - 1
        b[(x, y)] = color
        n += 1
        opp = "w" if color == "b" else "b"
        taken = []
        for nx, ny in neighbors(x, y):
            if b.get((nx, ny)) != opp:
                continue
            seen, stack, libs = {(nx, ny)}, [(nx, ny)], 0
            while stack:
                cx, cy = stack.pop()
                for ax, ay in neighbors(cx, cy):
                    v = b.get((ax, ay))
                    if v is None: libs += 1
                    elif v == opp and (ax, ay) not in seen:
                        seen.add((ax, ay)); stack.append((ax, ay))
            if libs == 0:
                for p in seen: b.pop(p, None)
                taken.append(seen)
        got = sum(len(s) for s in taken)
        if got:
            if color == "b": capW += got
            else: capB += got
            events.append((n, color, got, [L[px]+str(py+1) for s in taken for px, py in s]))
    return n, capB, capW, events, b

for name in ("maxsp_g1", "maxsp_g2", "selfplay_19"):
    p = os.path.join(r"F:\围棋\games", name, "moves.json")
    n, capB, capW, events, b = analyze(p)
    blacks = sum(1 for v in b.values() if v == "b")
    whites = sum(1 for v in b.values() if v == "w")
    print("== %s" % name)
    print("   落子 %d 手 | 黑被提 %d 子 / 白被提 %d 子 | 提子事件 %d 次" % (n, capB, capW, len(events)))
    print("   终局盘面: 黑 %d 子 + 白 %d 子 = %d 子, 空点 %d" % (blacks, whites, blacks+whites, 361-blacks-whites))
    for e in events[:6]:
        print("     第%3d手 白棋提%d子: %s" % (e[0], e[2], ",".join(e[3][:14])) if e[1]=="b"
              else "     第%3d手 黑棋提%d子: %s" % (e[0], e[2], ",".join(e[3][:14])))
    if len(events) > 6:
        big = sorted(events, key=lambda e: -e[2])[:3]
        for e in big:
            print("     最大: 第%3d手 %s 提%d子" % (e[0], "白提黑" if e[1]=="b" else "黑提白", e[2]))