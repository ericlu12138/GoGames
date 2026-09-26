# -*- coding: utf-8 -*-
"""从 maxsp_g1 的 GTP 日志里提取已下的着法(引擎崩溃前,146 手)。"""
import json, os, re
S = r"F:\围棋\games\maxsp_g1"
log = open(os.path.join(S, "logs", "gtp.log"), encoding="utf-8").read().splitlines()
moves = []
for i, ln in enumerate(log):
    m = re.match(r"^\[(B|W)\] >>> genmove ([bw])\s*$", ln)
    if not m:
        continue
    # 下一行应是 <<< 着法(忽略空应答)
    for j in range(i + 1, min(i + 4, len(log))):
        mm = re.match(r"^\[(B|W)\] <<< ([A-Ta-t]\d{1,2}|pass|PASS)\s*$", log[j])
        if mm:
            moves.append({"color": mm.group(1).lower(), "coord": mm.group(2).upper(), "sec": None})
            break
print("提取着法:", len(moves), "| 首手:", moves[0] if moves else None, "| 末手:", moves[-1] if moves else None)
# 校验颜色交替
bad = [i for i, mv in enumerate(moves, 1)
       if mv["color"] != ("b" if i % 2 == 1 else "w")]
print("颜色交替异常:", bad if bad else "无")
data = {"size": 19, "komi": 7.5, "max_time": 10, "max_visits": 100000, "threads": 16,
        "no_noise": True, "mode": "katago-selfplay-max", "interrupted": True,
        "resume_from": len(moves), "moves": moves}
json.dump(data, open(os.path.join(S, "moves_partial.json"), "w", encoding="utf-8"),
          ensure_ascii=False, indent=1)
print("已保存 moves_partial.json")