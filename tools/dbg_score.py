# -*- coding: utf-8 -*-
import json, os, re, subprocess, threading, time
KG = r"F:\围棋\KataGo-opencl"
NET = os.path.join(KG,"kata1-tf3-b11c768-s11500M-d6163M.bin.gz")
CFG = os.path.join(KG,"gtp_play.cfg")

def run(moves, budget=20.0, label=""):
    side = "b" if len(moves) % 2 == 0 else "w"
    p = subprocess.Popen([os.path.join(KG,"katago.exe"),"gtp","-model",NET,"-config",CFG],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, cwd=KG,
        universal_newlines=True, encoding="utf-8", errors="replace", bufsize=1)
    lines=[]
    def rd():
        for ln in p.stdout: lines.append(ln.rstrip("\r\n"))
    t=threading.Thread(target=rd); t.daemon=True; t.start()
    def gtp(c):
        lines.clear(); p.stdin.write(c+"\n"); p.stdin.flush()
        t0=time.time()
        while time.time()-t0<60:
            if len(lines)>=2 and lines[-1].strip()=="": break
            time.sleep(0.05)
        return [x for x in lines if x.strip()]
    gtp("boardsize 19"); gtp("komi 7.5")
    n=0
    for c,mv in moves:
        r=gtp("play %s %s"%(c,mv))
        if r and not r[0].startswith("="): print("  !! play fail", c, mv, r[0][:90])
        else: n+=1
    lines.clear()
    p.stdin.write("kata-analyze %s interval 100 maxmoves 4\n"%side); p.stdin.flush()
    t0=time.time(); best=""
    while time.time()-t0<budget:
        time.sleep(0.5)
        c=[l for l in lines if l.startswith("info ") and "scoreLead" in l]
        if c: best=c[-1]
    p.kill()
    sl=re.search(r"scoreLead (-?[0-9.]+)",best); wr=re.search(r"winrate ([0-9.]+)",best)
    vs=re.search(r"visits (\d+)",best)
    sw = (sl and float(sl.group(1))) or 0
    print("%-28s 手数=%3d 轮到=%s visits=%s winrate(%s)=%s scoreLead(白)=%.1f  [%s]" % (
        label, len(moves), side, vs.group(1) if vs else "?", side,
        wr.group(1) if wr else "?", sw if side=="w" else -sw, best[:80]))

run([], 20, "空盘19路")
run([("b","D4"),("w","Q16"),("b","Q4"),("w","D16")], 20, "4手常规开局")
d=json.load(open(r"F:\围棋\games\g20260921\moves.json",encoding="utf-8"))
ms=[(m["color"],m["coord"]) for m in d["moves"] if m["coord"].upper() not in ("PASS","RESIGN")]
run(ms, 20, "本局第%d手"%len(ms))