# -*- coding: utf-8 -*-
"""按标题找 GoDojo 窗口 -> 置顶 -> 截图
(枚举部分用已验证可用的最简写法,不设任何 argtypes)
"""
import ctypes
import sys
import time
from ctypes import wintypes

try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)      # 要物理像素坐标,否则裁图会只裁到左上四分之一
except Exception:
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass

u32 = ctypes.windll.user32

rows = []


def cb(h, _):
    if not u32.IsWindowVisible(h):
        return True
    n = u32.GetWindowTextLengthW(h)
    if n <= 0:
        return True
    b = ctypes.create_unicode_buffer(n + 2)
    u32.GetWindowTextW(h, b, n + 2)
    t = b.value
    if "GoDojo" in t or "围棋" in t:
        r = (ctypes.c_long * 4)()
        u32.GetWindowRect(h, ctypes.byref(r))
        rows.append((h, t, r[0], r[1], r[2] - r[0], r[3] - r[1]))
    return True


W = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
u32.EnumWindows(W(cb), 0)

print("匹配到的主窗口:")
for r in rows:
    print("   hwnd=%s pos=(%s,%s) size=%sx%s title=%r" % r)

# 挑最大的那个(排除提示条小窗)
rows = [r for r in rows if r[4] > 200 and r[5] > 200]
if not rows:
    print("没有可见的 GoDojo 主窗口")
    sys.exit(2)

hwnd, title, x, y, w, h = rows[0]
u32.ShowWindow(hwnd, 9)
u32.SetForegroundWindow(hwnd)
time.sleep(2.5)

from PIL import ImageGrab
full = ImageGrab.grab()
print("整屏:", full.size)
box = (max(0, x), max(0, y), min(full.size[0], x + w), min(full.size[1], y + h))
crop = full.crop(box)
print("窗口区域:", box, "->", crop.size)

w2 = 1300
crop.resize((w2, int(crop.size[1] * w2 / crop.size[0]))).save(r"D:\GoDojoBuild\screen.png")
print("已保存 D:\\GoDojoBuild\\screen.png")
