# -*- coding: utf-8 -*-
import json, os, subprocess, time
KG = r"F:\围棋\KataGo-opencl"
d = json.load(open(r"F:\围棋\games\g20260921\moves.json", encoding="utf-8"))
p = subprocess.Popen([os.path.join(KG,"katago.exe"),"gtp","-model",os.path.join(KG,"kata1-tf3-b11c768-s11500M-d6163M.bin.gz"),"-config",os.path.join(KG,"gtp_play.cfg")],
    stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, cwd=KG,
    universal_newlines=True, encoding="utf-8", errors="replace", bufsize=1)
def cmd(c, show=True):
    p.stdin.write(c+"\n"); p.stdin.flush()
    out=[]
    while True:
        ln=p.stdout.readline()
        if not ln: break
        s=ln.rstrip("\r\n")
        if s.strip()=="": break
        out.append(s)
    if show: print(">>>", c, "\n   <<<", " / ".join(out)[:200])
    return out
cmd("boardsize 19"); cmd("komi 7.5"); cmd("kata-set-param maxTime 5")
bad=0
for i,m in enumerate(d["moves"],1):
    if m["coord"].upper() in ("PASS","RESIGN"): continue
    r = cmd("play %s %s" % (m["color"], m["coord"]), show=False)
    if not r or not r[0].startswith("="):
        bad+=1
        print("非法/失败 第%d手 %s %s -> %s" % (i, m["color"], m["coord"], " ".join(r)[:120]))
        if bad>5: break
print("总手数", len(d["moves"]), "失败数", bad)
cmd("showboard")
p.kill()