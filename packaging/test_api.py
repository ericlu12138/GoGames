# -*- coding: utf-8 -*-
"""GoDojo Web 版 API 冒烟测试(不属于项目代码,放在构建目录)"""
import sys, os, time, json, urllib.request

sys.path.insert(0, r"F:\围棋\webapp")
import server as srvmod
from core import load_config

cfg = load_config()
srv, port, _ = srvmod.start_server(cfg, port=8811)
base = "http://127.0.0.1:%d" % port


def get(p):
    with urllib.request.urlopen(base + p, timeout=30) as r:
        return json.loads(r.read().decode())


def post(p, d=None):
    req = urllib.request.Request(base + p, data=json.dumps(d or {}).encode("utf-8"),
                                 headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=90) as r:
        return json.loads(r.read().decode())


def wait_idle(limit=120):
    for _ in range(limit):
        s = get("/api/state")
        if not s["busy"]:
            return s
        time.sleep(0.5)
    return get("/api/state")


fails = []


def check(name, cond, extra=""):
    print(("  [OK]   " if cond else "  [FAIL] ") + name + ("  " + str(extra) if extra else ""))
    if not cond:
        fails.append(name)


print("== 1. 等待引擎 ==")
s = None
for _ in range(60):
    s = get("/api/state")
    if s["engine"]["ready"] or "失败" in s["engine"]["msg"]:
        break
    time.sleep(1)
print("   engine.ready =", s["engine"]["ready"], "| msg =", s["engine"]["msg"])
check("引擎就绪", s["engine"]["ready"], s["engine"]["msg"])
if not s["engine"]["ready"]:
    raise SystemExit("引擎没起来,后面没法测")

print("== 2. 开新局(9 路 · 人执黑 · 60 visits)==")
print("  ", post("/api/new", {"size": 9, "human": "B", "handicap": 0,
                              "opponent": "ai", "visits": 60}))
time.sleep(1.5)
s = get("/api/state")
check("棋盘切到 9 路", s["size"] == 9, s["size"])
check("grid 是 9x9", len(s["grid"]) == 9 and len(s["grid"][0]) == 9)
check("黑先行", s["turn"] == "B", s["turn"])
check("开局 0 手", len(s["moves"]) == 0, len(s["moves"]))

print("== 3. 非法着法应被拒绝 ==")
d = post("/api/play", {"coord": "Z9"})
check("超范围坐标被拒", not d["ok"], d)
d = post("/api/play", {"coord": "J9"})      # 9 路最大是 J
check("9 路 J9 合法", d["ok"], d)
s = wait_idle()
check("AI 已应手", len(s["moves"]) == 2, s["moves"])
d = post("/api/play", {"coord": "J9"})
check("重复落子被拒", not d["ok"], d)

print("== 4. 目差/胜率 ==")
print("   eval =", json.dumps(s["eval"], ensure_ascii=False)[:200])
check("有候选点", len(s["eval"]["cands"]) >= 1, len(s["eval"]["cands"]))
check("有胜率换算", s["eval"]["winrate"] is not None, s["eval"]["winrate"])

print("== 5. 提示 / 悔棋 / 停一手 ==")
print("  ", post("/api/hint"))
time.sleep(4)
s = get("/api/state")
check("提示点返回", len(s["hint"]) >= 1, s["hint"])

n0 = len(s["moves"])
print("  ", post("/api/undo"))
time.sleep(0.5)
s = get("/api/state")
check("悔棋退 2 手", len(s["moves"]) == n0 - 2, (n0, len(s["moves"])))

print("  ", post("/api/analyze"))
time.sleep(4)
s = get("/api/state")
check("分析返回状态", s["status"] == "分析完成", s["status"])

print("== 6. 保存棋谱 ==")
d = post("/api/save")
print("   ", d)
check("SGF 已写盘", bool(d.get("path")) and os.path.exists(d["path"]), d.get("path"))

print("== 7. 设置 / 探测接口 ==")
d = get("/api/detect")
check("detect.found", d["found"], d["notes"])
s = get("/api/state")
check("state 带 engine.paths", "paths" in s["engine"], list(s["engine"].keys()))

print("== 8. 让子局(白先行)==")
post("/api/new", {"size": 9, "human": "B", "handicap": 3, "opponent": "ai", "visits": 60})
time.sleep(2.5)
s = get("/api/state")
check("让子局 komi=0.5", abs(s["komi"] - 0.5) < 1e-6, s["komi"])
check("让 3 子已摆上", len(s["moves"]) >= 3, s["moves"])
check("让子局该白走", s["turn"] == "W", s["turn"])

print()
print("=" * 56)
print("失败项:", fails if fails else "无 —— 全部通过")

# 收尾:关引擎,停服务
try:
    sess = srvmod.Handler.session
    if sess.engine and sess.engine.p and sess.engine.p.poll() is None:
        sess.engine.p.kill()
except Exception:
    pass
srv.shutdown()
print("服务已关闭")
