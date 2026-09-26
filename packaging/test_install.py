# -*- coding: utf-8 -*-
"""端到端功能测试:启动已"安装"的 GoDojo,验证接口与引擎

验证项:
  1. 进程能起来
  2. /api/state 能拿到棋盘状态
  3. 引擎最终 ready(且能看到用的是 GPU 还是 CPU)
  4. 能开新局并落子,引擎会应手
  5. 关掉后 katago 进程不残留
"""
import os
import sys
import json
import time
import subprocess
import urllib.request

SIM = r"D:\GoDojoBuild\sim_install"
EXE = os.path.join(SIM, "GoDojo.exe")
PORT = 8899
BASE = "http://127.0.0.1:%d" % PORT


def api(path, data=None, timeout=30):
    url = BASE + path
    if data is None:
        req = urllib.request.Request(url)
    else:
        body = json.dumps(data).encode("utf-8")
        req = urllib.request.Request(url, data=body,
                                     headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def main():
    print("=" * 62)
    print("GoDojo 安装版 · 端到端功能测试")
    print("=" * 62)

    # 清残留
    subprocess.run(["taskkill", "/F", "/IM", "katago.exe"],
                   capture_output=True, creationflags=0x08000000)
    time.sleep(1)

    print("\n[1] 启动程序 (--shell none --port %d)" % PORT)
    p = subprocess.Popen([EXE, "--shell", "none", "--port", str(PORT)],
                         creationflags=0x08000000)
    ok_all = True
    try:
        # 等服务起来
        st = None
        for i in range(40):
            time.sleep(1)
            if p.poll() is not None:
                print("   !! 进程退出 rc=%s" % p.poll())
                return 1
            try:
                st = api("/api/state", timeout=3)
                print("   服务已响应 (%.1fs)" % (i + 1))
                break
            except Exception:
                continue
        if st is None:
            print("   !! 服务未起来")
            return 1

        print("\n[2] 棋盘状态")
        print("   size=%s komi=%s human=%s turn=%s" % (st["size"], st["komi"],
                                                       st["human"], st["turn"]))
        print("   引擎消息:", st["engine"]["msg"])

        print("\n[3] 等引擎就绪(最多 60s)")
        label = ""
        for i in range(60):
            st = api("/api/state", timeout=5)
            e = st["engine"]
            if e["ready"]:
                label = e.get("label", "")
                print("   引擎就绪 (%.1fs)  用的是: [%s]" % (i + 1, label))
                break
            if e.get("tries"):
                pass
            time.sleep(1)
        else:
            print("   !! 引擎未就绪")
            print("   msg:", st["engine"]["msg"])
            for t in st["engine"].get("tries", []):
                print("   try:", t)
            ok_all = False

        if label:
            print("\n[4] 开新局 + 落子")
            api("/api/new", {"size": 9, "human": "B", "handicap": 0,
                             "opponent": "builtin", "visits": 60})
            time.sleep(1)
            r = api("/api/play", {"coord": "E5"}, timeout=90)
            print("   我方 E5 -> ok=%s err=%s" % (r.get("ok"), r.get("error", "")))
            for i in range(90):
                time.sleep(1)
                st = api("/api/state", timeout=5)
                if not st["busy"] and len(st["moves"]) >= 2:
                    print("   引擎应手:", st["moves"][-1], "(%.0fs)" % (i + 1))
                    break
            else:
                print("   !! 引擎未应手")
                print("   状态:", st.get("status"))
                ok_all = False

            print("\n[5] 提子/悔棋")
            r = api("/api/undo", {}, timeout=30)
            st = api("/api/state", timeout=5)
            print("   悔棋后手数:", len(st["moves"]))

        print("\n[6] 退出并检查残留")
        try:
            api("/api/quit", {}, timeout=5)
        except Exception:
            pass
        time.sleep(4)
        r = subprocess.run(["tasklist", "/FI", "IMAGENAME eq katago.exe", "/FO", "CSV", "/NH"],
                           capture_output=True, creationflags=0x08000000)
        out = r.stdout.decode("gbk", errors="replace")
        left = [l for l in out.splitlines() if l.strip().startswith('"katago')]
        if left:
            print("   !! 残留 katago 进程:")
            for l in left:
                print("      " + l)
            ok_all = False
        else:
            print("   无残留 katago 进程 OK")

    finally:
        try:
            p.terminate()
            p.wait(timeout=8)
        except Exception:
            try:
                p.kill()
            except Exception:
                pass
        subprocess.run(["taskkill", "/F", "/IM", "katago.exe"],
                       capture_output=True, creationflags=0x08000000)

    print("\n" + "=" * 62)
    print("结果:", "全部通过 ✅" if ok_all else "有失败项 ❌")
    return 0 if ok_all else 1


if __name__ == "__main__":
    sys.exit(main())
