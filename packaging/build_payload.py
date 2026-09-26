# -*- coding: utf-8 -*-
"""组装 GoDojo 分发载荷

把散落在 F 盘 / 构建目录的资源集中到 dist_payload_full/,
再由 Inno Setup 编译成单文件安装包。

产出结构:
    dist_payload_full/
      config.json          相对路径配置(装到任何地方都能用)
      gtp_web.cfg          引擎配置(无绝对路径)
      使用说明.md
      KataGo-opencl/       GPU 引擎 katago.exe + *.dll
      KataGo-cpu/          CPU 引擎 katago.exe + *.dll
      models/              共享权重(只放一份)
      games/               空目录
      外接AI/              空目录
"""
import os
import re
import sys
import glob
import shutil

BUILD = r"D:\GoDojoBuild"
PAYLOAD = os.path.join(BUILD, "dist_payload_full")
F_ROOT = r"F:\围棋"

# 引擎目录里只需要这些文件,其余(README/示例配置/cacert)不带
KEEP_DLL = ("bz2.dll", "libcrypto-3-x64.dll", "libssl-3-x64.dll", "z.dll", "zip.dll",
            "msvcp140.dll", "msvcp140_1.dll", "msvcp140_2.dll", "msvcp140_atomic_wait.dll",
            "msvcp140_codecvt_ids.dll", "vcruntime140.dll", "vcruntime140_1.dll",
            "vcruntime140_threads.dll")

MODEL_NAME = "kata1-tf3-b11c768-s11500M-d6163M.bin.gz"


def step(msg):
    print("  " + msg)


def clean(path):
    if os.path.isdir(path):
        shutil.rmtree(path, ignore_errors=True)


def build_config():
    """分发用 config.json —— 全部相对路径,引擎留空让程序自动发现"""
    return """{
  "engine": {
    "katago": "",
    "model": "",
    "config": ""
  },
  "paths": {
    "games": "games",
    "external": "外接AI",
    "log": "godojo_web.log"
  },
  "game": {
    "size": 19,
    "human": "B",
    "handicap": 0,
    "visits": 120,
    "komi": 7.5
  },
  "startup": {
    "killStaleEngine": false
  },
  "server": {
    "host": "127.0.0.1",
    "port": 0
  }
}
"""


def build_gtp_cfg():
    """把 F 盘 gtp_practice.cfg 里的绝对路径清掉,做成通用配置"""
    src = os.path.join(F_ROOT, "KataGo-opencl", "gtp_practice.cfg")
    txt = open(src, encoding="utf-8", errors="replace").read()
    out = []
    for line in txt.splitlines():
        s = line.strip()
        # 注释掉任何含绝对路径的设置(logDir / homeDataDir 等)
        if s and not s.startswith("#") and re.search(r"[A-Za-z]:[\\/]", s):
            out.append("# [GoDojo 分发版已注释] " + line)
            continue
        out.append(line)
    body = "\n".join(out)
    header = (
        "# GoDojo 围棋道场 · 引擎配置(分发版)\n"
        "# 本文件由 GoDojo 提供,基于 KataGo 官方 gtp_example.cfg 精简。\n"
        "# 所有路径均为相对/自动,不要把绝对路径写进来。\n"
        "#\n"
        "# 常用调节项(改完保存,重启软件生效):\n"
        "#   maxTime            每手最多思考秒数(越小越快,越大越强)\n"
        "#   numSearchThreads   CPU 搜索线程数(可设成本机核心数)\n"
        "#   allowResignation   是否允许引擎认输(默认 false,便于学习)\n"
        "#\n"
    )
    return header + body + "\n"


def main():
    print("=" * 62)
    print("组装 GoDojo 分发载荷")
    print("=" * 62)

    clean(PAYLOAD)
    os.makedirs(PAYLOAD)

    # ---- 1. 配置 ----
    print("\n[1/6] 配置")
    with open(os.path.join(PAYLOAD, "config.json"), "w", encoding="utf-8", newline="\n") as f:
        f.write(build_config())
    step("config.json")
    with open(os.path.join(PAYLOAD, "gtp_web.cfg"), "w", encoding="utf-8", newline="\n") as f:
        f.write(build_gtp_cfg())
    step("gtp_web.cfg (已清除绝对路径)")

    # ---- 2. 双引擎 ----
    print("\n[2/6] 引擎")
    for eng in ("KataGo-opencl", "KataGo-cpu"):
        sdir = os.path.join(F_ROOT, eng)
        ddir = os.path.join(PAYLOAD, eng)
        os.makedirs(ddir)
        k = os.path.join(sdir, "katago.exe")
        if not os.path.isfile(k):
            print("  !! 缺 %s" % k)
            return 1
        shutil.copy2(k, os.path.join(ddir, "katago.exe"))
        n = 0
        for dll in KEEP_DLL:
            sp = os.path.join(sdir, dll)
            if os.path.isfile(sp):
                shutil.copy2(sp, os.path.join(ddir, dll))
                n += 1
        step("%s: katago.exe + %d 个 DLL" % (eng, n))

    # ---- 3. 共享权重 ----
    print("\n[3/6] 权重")
    msrc = os.path.join(F_ROOT, "KataGo-opencl", MODEL_NAME)
    if not os.path.isfile(msrc):
        print("  !! 缺权重 %s" % msrc)
        return 1
    mdir = os.path.join(PAYLOAD, "models")
    os.makedirs(mdir)
    dst = os.path.join(mdir, MODEL_NAME)
    step("复制 %.1f MB ..." % (os.path.getsize(msrc) / 1048576.0))
    shutil.copy2(msrc, dst)
    step("models\\%s (%.1f MB)" % (MODEL_NAME, os.path.getsize(dst) / 1048576.0))

    # ---- 3b. GPU 调优缓存(同款显卡的用户可免掉 5-10 分钟首次调优) ----
    # KataGo 按"当前工作目录/KataGoData/opencltuning"存放调优结果,文件名含
    # GPU 型号。带上开发机这份:同款显卡命中即秒起;不同显卡 KataGo 会自己
    # 重新调优(文件名不匹配),不会出错。
    tune_src = os.path.join(F_ROOT, "KataGo-opencl", "KataGoData", "opencltuning")
    if os.path.isdir(tune_src):
        tune_dst = os.path.join(PAYLOAD, "KataGo-opencl", "KataGoData", "opencltuning")
        os.makedirs(tune_dst, exist_ok=True)
        n = 0
        for f in os.listdir(tune_src):
            if f.endswith(".txt"):
                shutil.copy2(os.path.join(tune_src, f), os.path.join(tune_dst, f))
                step("预热缓存: " + f)
                n += 1
        if not n:
            step("(无调优缓存可带)")
    else:
        step("(开发机尚无调优缓存,跳过)")

    # ---- 4. 空目录 ----
    print("\n[4/6] 数据目录")
    for d in ("games", "外接AI"):
        os.makedirs(os.path.join(PAYLOAD, d), exist_ok=True)
        step(d + "\\")

    # ---- 5. 使用说明 ----
    print("\n[5/6] 使用说明")
    doc = os.path.join(BUILD, "dist_payload", "使用说明.md")
    if os.path.isfile(doc):
        shutil.copy2(doc, os.path.join(PAYLOAD, "使用说明.md"))
        step("使用说明.md (来自 dist_payload)")
    else:
        step("(未找到现成说明,跳过)")

    # ---- 6. 校验 ----
    print("\n[6/6] 校验")
    total = 0
    for root, dirs, files in os.walk(PAYLOAD):
        for f in files:
            total += os.path.getsize(os.path.join(root, f))
    print()
    print("-" * 62)
    for root, dirs, files in os.walk(PAYLOAD):
        rel = os.path.relpath(root, PAYLOAD)
        rel = "" if rel == "." else rel + "\\"
        sz = sum(os.path.getsize(os.path.join(root, f)) for f in files)
        print("  %-22s %3d files  %8.1f MB" % (rel or "(根)", len(files), sz / 1048576.0))
    print("-" * 62)
    print("  合计 %.1f MB" % (total / 1048576.0))
    print()
    print("载荷就绪:", PAYLOAD)
    return 0


if __name__ == "__main__":
    sys.exit(main())
