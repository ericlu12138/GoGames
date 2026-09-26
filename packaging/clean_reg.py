# -*- coding: utf-8 -*-
"""清除 GoDojo 测试安装留下的注册表残留(需管理员权限)

背景:测试安装卸载后,Inno Setup 在 HKLM 的 Uninstall 键下留了一条记录,
指向已删除的测试目录。这条记录会让安装包误判"已安装",静默模式下直接
退出(退出码 2)。
"""
import os
import sys
import ctypes
import winreg

KEY = (r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"
       r"\{8F3A5C21-4D7B-4E96-9A1F-6B2C8E4D7A53}_is1")
LOG = r"D:\GoDojoBuild\del_key.log"


def main():
    lines = []
    lines.append("admin=%s" % bool(ctypes.windll.shell32.IsUserAnAdmin()))

    # 1) 列出所有含 GoDojo 的 Uninstall 条目
    roots = [
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall", "HKLM"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall", "HKLM32"),
        (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall", "HKCU"),
    ]
    found = []
    for hive, path, tag in roots:
        try:
            k = winreg.OpenKey(hive, path)
        except Exception:
            continue
        try:
            n = winreg.QueryInfoKey(k)[0]
        except Exception:
            continue
        for i in range(n):
            try:
                sub = winreg.EnumKey(k, i)
                sk = winreg.OpenKey(k, sub)
                try:
                    name = str(winreg.QueryValueEx(sk, "DisplayName")[0])
                except Exception:
                    continue
                if "GoDojo" in name or "围棋" in name:
                    found.append((hive, tag, sub, name))
            except Exception:
                pass
    lines.append("找到 %d 个相关条目" % len(found))
    for hive, tag, sub, name in found:
        lines.append("  [%s] %s -> %s" % (tag, sub, name))

    # 2) 逐个删除
    ok = 0
    for hive, tag, sub, name in found:
        try:
            winreg.DeleteKey(hive, sub)
            lines.append("  已删除 [%s] %s" % (tag, sub))
            ok += 1
        except Exception as e:
            lines.append("  删除失败 [%s] %s -> %s" % (tag, sub, e))

    # 3) 直接删目标键(以防上面没枚举到)
    try:
        winreg.DeleteKey(winreg.HKEY_LOCAL_MACHINE, KEY)
        lines.append("直接删除目标键: OK")
    except FileNotFoundError:
        lines.append("直接删除目标键: 本来就不存在")
    except Exception as e:
        lines.append("直接删除目标键: 失败 %s" % e)

    # 4) 验证
    try:
        winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, KEY)
        lines.append("验证: 键仍存在 ❌")
    except FileNotFoundError:
        lines.append("验证: 键已清除 ✅")
    except Exception as e:
        lines.append("验证出错: %s" % e)

    lines.append("已删除 %d 条" % ok)
    txt = "\n".join(lines)
    try:
        with open(LOG, "w", encoding="utf-8") as f:
            f.write(txt)
    except Exception:
        pass
    print(txt)
    return 0


if __name__ == "__main__":
    sys.exit(main())
