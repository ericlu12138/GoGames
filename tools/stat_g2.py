# -*- coding: utf-8 -*-
import json, os, statistics
S = r"F:\围棋\games\maxsp_g2"
d = json.load(open(os.path.join(S, "moves.json"), encoding="utf-8"))
mv = d["moves"]
secs = [m["sec"] for m in mv if m.get("sec")]
print("总手数:", len(mv), "(含 pass)", "| 实际落子:", len([m for m in mv if m["coord"].upper()!="PASS"]))
print("final_score:", d["final_score"], "| 每手平均 %.1fs 最长 %.1fs" % (statistics.mean(secs), max(secs)))
print("强度参数:", json.dumps(d.get("strength_params", {}), ensure_ascii=False))
print("前 20 手:", ",".join(("%s%s" % (m["color"].upper(), m["coord"])) for m in mv[:20]))
print("最后 6 手:", ",".join(("%s%s" % (m["color"].upper(), m["coord"])) for m in mv[-6:]))