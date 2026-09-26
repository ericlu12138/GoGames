# -*- coding: utf-8 -*-
"""顺序跑 N 局最高强度自战,每局都用"可自动重启"的续下脚本,崩了也不会丢棋谱。

用法: python -u run_games.py g3 g4   (会话目录为 F:\围棋\games\<名字>)
"""
import os, subprocess, sys, time

PY = r"D:\Anaconda3\python.exe"
SCRIPT = r"F:\围棋\_辅助脚本\selfplay_resume.py"
BASE = r"F:\围棋\games"

for name in sys.argv[1:]:
    sdir = os.path.join(BASE, name)
    os.makedirs(os.path.join(sdir, "logs"), exist_ok=True)
    part = os.path.join(sdir, "moves_partial.json")
    if not os.path.exists(part):
        with open(part, "w", encoding="utf-8") as f:
            f.write('{"size":19,"komi":7.5,"moves":[],"mode":"katago-selfplay-max"}')
    print("=== 开始 %s  %s ===" % (name, time.strftime("%H:%M:%S")), flush=True)
    rc = subprocess.call([PY, "-u", SCRIPT, "--session", sdir,
                          "--max-time", "10", "--max-visits", "100000", "--threads", "16"])
    print("=== %s 结束 rc=%d  %s ===" % (name, rc, time.strftime("%H:%M:%S")), flush=True)