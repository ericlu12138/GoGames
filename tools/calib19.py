# -*- coding: utf-8 -*-
"""校正测试:构造白方明确活棋的局面,看 scoreLead 是否合理(验证打分/形势判断是否可信)。"""
import os, re, subprocess, threading, time
KG = r"F:\围棋\KataGo-opencl"
def test(plays, komi, label, secs=15):
    p = subprocess.Popen([os.path.join(KG,"katago.exe"),"gtp","-model",
        os.path.join(KG,"kata1-tf3-b11c768-s11500M-d6163M.bin.gz"),"-config",os.path.join(KG,"gtp_play.cfg")],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, cwd=KG,
        universal_newlines=True, encoding="utf-8", errors="replace", bufsize=1)
    lines=[]
    threading.Thread(target=lambda: [lines.append(l.rstrip("\r\n")) for l in p.stdout], daemon=True).start()
    def gtp(c, t=60):
        lines.clear(); p.stdin.write(c+"\n"); p.stdin.flush()
        t0=time.time()
        while time.time()-t0<t:
            if lines and lines[-1].strip()=="": break
            time.sleep(0.05)
        return [x for x in lines if x.strip()]
    gtp("boardsize 19"); gtp("komi %g"%komi)
    gtp("kata-set-param maxVisits 800")
    for c,mv in plays: gtp("play %s %s"%(c,mv))
    side = "b" if len(plays)%2==0 else "w"
    lines.clear(); p.stdin.write("kata-analyze %s interval 100 maxmoves 1\n"%side); p.stdin.flush()
    t0=time.time(); best=""
    while time.time()-t0<secs:
        time.sleep(0.5)
        c=[l for l in lines if l.startswith("info ") and "scoreLead" in l]
        if c: best=c[-1]
    sl=re.search(r"scoreLead (-?[0-9.]+)",best); wr=re.search(r"winrate ([0-9.]+)",best)
    w = float(wr.group(1)) if wr else 0; s = float(sl.group(1)) if sl else 0
    # 统一为白视角(area scoring: 空点归属由双方势力决定)
    if side=="b": s = -s
    print("%-22s 白目差 %+8.1f  白胜率 %5.1f%%" % (label, s, (w if side=="w" else 1-w)*100))
    p.kill()

test([], 7.5, "空盘")
test([("b","D4"),("w","Q16"),("b","Q4"),("w","D16")], 7.5, "4手开局")
test([("b","Q16"),("w","D4"),("b","Q4"),("w","D16"),("b","K10")], 7.5, "5手+天元")