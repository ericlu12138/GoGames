# -*- coding: utf-8 -*-
"""验证 max 强度相关参数是否可设置(kata-set-param),避免踩配置坑。"""
import os, subprocess, sys, threading, time
KG = r"F:\围棋\KataGo-opencl"
p = subprocess.Popen([os.path.join(KG,"katago.exe"),"gtp","-model",
    os.path.join(KG,"kata1-tf3-b11c768-s11500M-d6163M.bin.gz"),"-config",os.path.join(KG,"gtp_play.cfg")],
    stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, cwd=KG,
    universal_newlines=True, encoding="utf-8", errors="replace", bufsize=1)
lines=[]
threading.Thread(target=lambda: [lines.append(l.rstrip("\r\n")) for l in p.stdout], daemon=True).start()
def cmd(c, t=60):
    lines.clear(); p.stdin.write(c+"\n"); p.stdin.flush()
    t0=time.time()
    while time.time()-t0<t:
        if lines and lines[-1].strip()=="": break
        time.sleep(0.05)
    return " | ".join(x for x in lines if x.strip())
print("boardsize:", cmd("boardsize 19")[:40] or "(ok)")
tests = [
 "kata-set-param maxVisits 100000",
 "kata-set-param maxTime 999",
 "kata-set-param numSearchThreads 16",
 "kata-set-param rootNoiseEnabled false",
 "kata-set-param chosenMoveTemperature 0",
 "kata-set-param chosenMoveTemperatureEarly 0",
 "kata-set-param analysisWideRootNoise 0",
 "kata-set-param ponderingEnabled false",
 "kata-set-param lagBuffer 1.0",
 "kata-set-param dynamicPlayoutDoublingAdvantageCapPerOppLead 0",
]
for t in tests:
    r = cmd(t)
    ok = r.startswith("=")
    print(("  ✓ " if ok else "  ✗ ") + t + ("" if ok else "   -> " + r[:90]))
p.kill()