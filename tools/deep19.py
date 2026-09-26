# -*- coding: utf-8 -*-
"""用高访问量对终局局面做形势判断,并列出黑方候选点(赛后复盘用)。"""
import json, os, re, subprocess, threading, time
KG = r"F:\围棋\KataGo-opencl"
d = json.load(open(r"F:\围棋\games\g20260921\moves.json", encoding="utf-8"))
moves=[m for m in d["moves"] if m["coord"].upper() not in ("PASS","RESIGN")]
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
gtp("boardsize 19"); gtp("komi 7.5")
gtp("kata-set-param maxTime 25"); gtp("kata-set-param maxVisits 3000"); gtp("kata-set-param ponderingEnabled false")
for m in moves: gtp("play %s %s"%(m["color"],m["coord"]))
side = "b" if len(moves)%2==0 else "w"
lines.clear(); p.stdin.write("kata-analyze %s interval 200 maxmoves 6\n"%side); p.stdin.flush()
t0=time.time(); best=""
while time.time()-t0 < 45:
    time.sleep(0.5)
    c=[l for l in lines if l.startswith("info ") and "scoreLead" in l]
    if c: best=c[-1]
wr=re.search(r"winrate ([0-9.]+)",best); sl=re.search(r"scoreLead (-?[0-9.]+)",best)
vs=re.search(r"visits (\d+)",best)
print("deep search: visits=%s winrate(%s)=%s scoreLead=%s" % (vs.group(1) if vs else "?", side,
      wr.group(1) if wr else "?", sl.group(1) if sl else "?"))
if sl and wr:
    s=float(sl.group(1)); w=float(wr.group(1))
    if side=="b": s, w = -s, 1-w
    print("白视角: 胜率 %.1f%%  目差 %+.1f" % (w*100, s))
p.kill()