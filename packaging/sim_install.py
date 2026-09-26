# -*- coding: utf-8 -*-
"""模拟安装:把应用 + 载荷铺成"装完之后的样子",用于端到端验证

模拟目录 D:\\GoDojoBuild\\sim_install\\  (= 将来用户的 D:\\GoDojo)
铺完直接启动 exe,看能不能开对局、能不能自动挑引擎。
"""
import os
import sys
import shutil
import subprocess
import time

BUILD = r"D:\GoDojoBuild"
SIM = os.path.join(BUILD, "sim_install")
APP = os.path.join(BUILD, "dist", "GoDojo")
PAY = os.path.join(BUILD, "dist_payload_full")


def main():
    print("=" * 62)
    print("模拟安装 ->", SIM)
    print("=" * 62)

    if os.path.isdir(SIM):
        shutil.rmtree(SIM, ignore_errors=True)
    os.makedirs(SIM)

    # 1) 应用本体
    print("\n[1] 应用本体")
    for name in ("GoDojo.exe", "_internal"):
        s = os.path.join(APP, name)
        d = os.path.join(SIM, name)
        if os.path.isdir(s):
            shutil.copytree(s, d)
        else:
            shutil.copy2(s, d)
    # web/ 提到外层(web_dir() 优先读这里)
    shutil.copytree(os.path.join(APP, "_internal", "web"), os.path.join(SIM, "web"))
    print("    GoDojo.exe + _internal\\ + web\\")

    # 2) 配置
    print("\n[2] 配置")
    for f in ("config.json", "gtp_web.cfg", "使用说明.md"):
        shutil.copy2(os.path.join(PAY, f), os.path.join(SIM, f))
        print("    " + f)

    # 3) 引擎 + 权重 + 数据目录
    print("\n[3] 引擎 / 权重 / 数据目录")
    for sub in ("KataGo-opencl", "KataGo-cpu", "models", "games", "外接AI"):
        s = os.path.join(PAY, sub)
        d = os.path.join(SIM, sub)
        if os.path.isdir(s):
            if sub in ("games", "外接AI"):
                os.makedirs(d, exist_ok=True)
            else:
                shutil.copytree(s, d)
            print("    " + sub + "\\")

    # 4) 校验
    print("\n[4] 校验目录")
    total = 0
    for root, dirs, files in os.walk(SIM):
        for f in files:
            total += os.path.getsize(os.path.join(root, f))
    print("    合计 %.1f MB" % (total / 1048576.0))

    # 5) 语法层面确认程序能找到引擎(用安装目录身份 import 源码 core)
    print("\n[5] 以安装目录身份检查引擎发现")
    check = r'''
import sys, os
sys.path.insert(0, r"{src}")
import core
core.base_dir = lambda: r"{sim}"          # 伪装成"以安装目录运行"
cfg = core.load_config(save_if_missing=False)
print("   config.json 读到 engine:", cfg["engine"])
cands = core.engine_candidates(cfg)
print("   候选引擎:")
for c in cands:
    print("      [%s] %s" % (c["label"], os.path.relpath(c["katago"], r"{sim}")))
    print("          model :", os.path.relpath(c["model"], r"{sim}"))
    print("          config:", os.path.relpath(c["config"], r"{sim}"))
if len(cands) < 2:
    print("   !! 预期 2 个候选(GPU + CPU),实际 %d" % len(cands))
    sys.exit(1)
for c in cands:
    for key in ("katago", "model", "config"):
        if not os.path.isfile(c[key]):
            print("   !! 文件不存在:", c[key]); sys.exit(1)
print("   所有候选文件实际存在 OK")
'''.format(src=os.path.join(BUILD, "src_dist"), sim=SIM)
    r = subprocess.run([sys.executable, "-c", check], capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    print(r.stdout.rstrip())
    if r.returncode != 0:
        print(r.stderr.rstrip()[-2000:])
        return 1
    r = subprocess.run([sys.executable, "-c", check], capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    print(r.stdout.rstrip())
    if r.returncode != 0:
        print(r.stderr.rstrip()[-2000:])
        return 1

    print("\n" + "=" * 62)
    print("模拟安装完成:", SIM)
    print("启动命令: \"%s\\GoDojo.exe\"" % SIM)
    return 0


if __name__ == "__main__":
    sys.exit(main())
