# -*- coding: utf-8 -*-
"""从 moves.json 出发让 KataGo 自战终局,并保存完整终局盘面。"""
import json, os, re, subprocess, sys, threading, time
KG = r"F:\围棋\KataGo-opencl"
session = sys.argv[1]
limit = int(sys.argv[2]) if len(sys.argv) > 2 else 150
d = json.load(open(os.path.join(session, "moves.json"), encoding="utf-8"))
p = subprocess.Popen([os.path.join(KG,"katago.exe"),"gtp","-model",
    os.path.join(KG,"kata1-tf3-b11c768-s11500M-d6163M.bin.gz"),"-config",os.path.join(KG,"gtp_play.cfg")],
    stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, cwd=KG,
    universal_newlines=True, encoding="utf-8", errors="replace", bufsize=1)
lines=[]
def rd():
    for ln in p.stdout: lines.append(ln.rstrip("\r\n"))
t=threading.Thread(target=rd); t.daemon=True; t.start()
def gtp(c, timeout=90):
    lines.clear(); p.stdin.write(c+"\n"); p.stdin.flush()
    t0=time.time()
    while time.time()-t0<timeout:
        if len(lines)>=1 and lines[-1].strip()=="": break
        time.sleep(0.05)
    return [x for x in lines if x.strip()]
gtp("boardsize 19"); gtp("komi 7.5")
gtp("kata-set-param maxTime 3"); gtp("kata-set-param ponderingEnabled false")
allmoves = []
for m in d["moves"]:
    if m["coord"].upper() in ("PASS","RESIGN"): continue
    gtp("play %s %s"%(m["color"],m["coord"])); allmoves.append((m["color"],m["coord"]))
n=len(allmoves); passes=0
log=[]
t0=time.time()
while passes<2 and n < len(allmoves)+limit and time.time()-t0 < 600:
    color = "b" if (n % 2 == 0) else "w"
    r = gtp("genmove %s"%color, timeout=60)
    mv=""
    for x in r:
        mm=re.search(r"\b(pass|resign|[A-Ta-t]\d{1,2})\b", x)
        if mm and x.startswith("="): mv=mm.group(1).upper(); break
    if not mv: mv="pass"
    allmoves.append((color,mv)); n+=1
    log.append("%3d %s %s" % (n, color.upper(), mv))
    if mv=="PASS": passes+=1
    else: passes=0
sb = gtp("showboard", 60)
fs = gtp("final_score", 60)
out = []
out.append("=== 自战终局 ===")
out.append("终局手数: %d" % n)
out.append("final_score: %s" % " ".join(fs))
out.append("--- 新增着法(自战部分) ---")
out.extend(log)
out.append("--- showboard ---")
out.extend(x for x in sb if x.strip())
open(os.path.join(session,"selfplay_final.txt"),"w",encoding="utf-8").write("\n".join(out))
print("\n".join(out[-30:]))
p.kill()