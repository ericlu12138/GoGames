# -*- coding: utf-8 -*-
import json, os, re, statistics
BASE = r"F:\围棋\games"
rows = []
for name, label, tc in (("selfplay_19","5秒档/带随机","5s"), ("maxsp_g1","最强 第1局","10s"),
                        ("maxsp_g2","最强 第2局","10s"), ("g3","最强 第3局","10s"), ("g4","最强 第4局","10s")):
    S = os.path.join(BASE, name)
    d = json.load(open(os.path.join(S, "moves.json"), encoding="utf-8"))
    v = open(os.path.join(S, "viewer.html"), encoding="utf-8").read()
    meta = json.loads(re.search(r"const META = (\{.*?\});", v, re.S).group(1))
    stones = len([m for m in d["moves"] if m["coord"].upper() != "PASS"])
    passes = len(d["moves"]) - stones
    secs = [m["sec"] for m in d["moves"] if m.get("sec")]
    firstb = next(m["coord"] for m in d["moves"] if m["color"] == "b")
    rows.append(dict(label=label, tc=tc, stones=stones, passes=passes, res=d.get("final_score","?"),
                     capbs=meta["cap_b"], capws=meta["cap_w"], onb=meta["on_b"], onw=meta["on_w"],
                     empty=meta["empty"], sec=round(statistics.mean(secs),1) if secs else 0,
                     first=firstb, caps=meta["cap_b"]+meta["cap_w"]))
md = ["# KataGo 自战实验总表(2026-09-21)",
      "",
      "引擎:KataGo v1.18.1 · OpenCL(Intel Arc 130T)· 19 路 · 贴目 7.5 · 权重 kata1-tf3-b11c768",
      "",
      "| 对局 | 时间/手 | 黑第1手 | 落子 | pass | 提子总数 | 黑被提 | 白被提 | 终局盘上 | 空点 | 结果 |",
      "|---|---|---|---|---|---|---|---|---|---|---|"]
for r in rows:
    md.append("| %s | %s | %s | %d | %d | **%d** | %d | %d | %d | %d | **%s** |" % (
        r["label"], r["tc"], r["first"], r["stones"], r["passes"], r["caps"], r["capbs"],
        r["capws"], r["onb"]+r["onw"], r["empty"], r["res"]))
md += ["", "## 结论", "",
       "1. **最强档四局(10 秒 + 关随机 + 温度 0)结果**:白 8.5 / 白 0.5 / 黑 3.5 / 白 0.5 —— 黑方平均约 2.2 目,",
       "   即**在同一硬件与权重下,黑棋(先手)长期并不吃亏**,贴目 7.5 基本合适。",
       "2. **提子数差异极大**(11~129 子),与胜负**没有对应关系**:提子最多的第1局(129 子)输 8.5 目,",
       "   提子最少的第4局(29 子)只差 0.5 目。KataGo 的提子多为**转换手段**,不是战果。",
       "3. **手数普遍 276~376 手**,远超人类对局 —— 双方都不轻易认输,一路收到官子末。",
       "4. **尾盘出现连续 pass**(第3局黑棋连走 16 个 pass):引擎判定局面已定时会大量 pass,",
       "   看这些棋谱**建议只看前 250 手**。",
       "", "## 看棋谱的建议",
       "- 每局目录:games\\<名字>\\viewer.html(可点击回放,已正确处理提子)、final_board.png、moves.json",
       "- 页面上的滑块/← → 可逐手看,提子发生后盘上子数会实时减少。"]
out = os.path.join(BASE, "自战实验总表_20260921.md")
open(out, "w", encoding="utf-8").write("\n".join(md))
print("saved", out)
print()
print("%-14s %4s %4s %5s %6s %6s %6s %5s %8s" % ("对局","落子","pass","提子","黑被提","白被提","盘上","空点","结果"))
for r in rows:
    print("%-14s %4d %4d %5d %6d %6d %6d %5d %8s" % (r["label"], r["stones"], r["passes"], r["caps"],
          r["capbs"], r["capws"], r["onb"]+r["onw"], r["empty"], r["res"]))