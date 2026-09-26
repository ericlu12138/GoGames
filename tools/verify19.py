# -*- coding: utf-8 -*-
"""核对:重放本局着法,输出最终盘面与形势(黑视角+白视角)。"""
import json, os, re, subprocess, threading, time, sys
KG = r"F:\围棋\KataGo-opencl"
session = r"F:\围棋\games\g20260921"
d = json.load(open(os.path.join(session,"moves.json"), encoding="utf-8"))
p = subprocess.Popen([os.path.join(KG,"katago.exe"),"gtp","-model",
    os.path.join(KG,"kata1-tf3-b11c768-s11500M-d6163M.bin.gz"),"-config",os.path.join(KG,"gtp_play.cfg")],
    stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, cwd=KG,
    universal_newlines=True, encoding="utf-8", errors="replace", bufsize=1)
lines=[]
def rd():
    for ln in p.stdout: lines.append(ln.rstrip("\r\n"))
threading.Thread(target=rd, daemon=True).start()
def gtp(c, timeout=120):
    lines.clear(); p.stdin.write(c+"\n"); p.stdin.flush()
    t0=time.time()
    while time.time()-t0<timeout:
        if lines and lines[-1].strip()=="": break
        time.sleep(0.05)
    return [x for x in lines if x.strip()]
gtp("boardsize 19"); gtp("komi 7.5"); gtp("kata-set-param maxTime 5")
for m in d["moves"]:
    if m["coord"].upper() in ("PASS","RESIGN"): continue
    gtp("play %s %s"%(m["color"],m["coord"]))
print("重放完成,盘上着手 =", len([m for m in d["moves"] if m["coord"].upper() not in ("PASS","RESIGN")]))
sb = gtp("showboard", 60)
for x in sb: print("  ", x)
# 长期分析: 各自视角
lines.clear(); p.stdin.write("kata-analyze b interval 500 maxmoves 5\n"); p.stdin.flush()
t0=time.time(); best=""
while time.time()-t0 < 30:
    time.sleep(0.5)
    c=[l for l in lines if l.startswith("info ") and "scoreLead" in l]
    if c: best=c[-1]
wr=re.search(r"winrate ([0-9.]+)", best); sl=re.search(r"scoreLead (-?[0-9.]+)", best)
vs=re.search(r"visits (\d+)", best)
if wr and sl:
    w=float(wr.group(1)); s=float(sl.group(1))
    print("形势(黑先手视角): 黑胜率 %.1f%%  目差 黑%s%.1f" % (w*100, "+" if s>=0 else "", s))
    print("换算白视角: 白胜率 %.1f%%  白目差 %+.1f" % ((1-w)*100, -s))
print("root visits:", vs.group(1) if vs else "?")
p.kill()