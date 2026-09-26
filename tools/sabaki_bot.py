# -*- coding: utf-8 -*-
"""Sabaki 自动读盘 + 自动落子机器人
用法:
  python sabaki_bot.py read               # 打印当前盘面
  python sabaki_bot.py click Q16          # 在 Sabaki 棋盘上点击 Q16
  python sabaki_bot.py watch              # 轮询:对手落子后打印盘面并退出(用于唤醒我)
"""
import sys, os, time, json, ctypes
from ctypes import wintypes
import numpy as np
from PIL import Image, ImageGrab

LETTERS = "ABCDEFGHJKLMNOPQRST"
STATE = r"D:\Go\sabaki_state.json"

# 关键:声明 DPI 感知,否则窗口坐标(逻辑像素)与截屏(物理像素)不一致,会截偏
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)      # PROCESS_PER_MONITOR_DPI_AWARE
except Exception:
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass

user32 = ctypes.windll.user32


class RECT(ctypes.Structure):
    _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long),
                ("right", ctypes.c_long), ("bottom", ctypes.c_long)]


def find_window(keyword="Sabaki"):
    """找 Sabaki 主窗口;跳过最小化窗口(坐标 -32000)"""
    result = []

    def cb(hwnd, lparam):
        if not user32.IsWindowVisible(hwnd):
            return True
        if user32.IsIconic(hwnd):          # 最小化 -> 跳过
            return True
        n = user32.GetWindowTextLengthW(hwnd)
        if n == 0:
            return True
        buf = ctypes.create_unicode_buffer(n + 2)
        user32.GetWindowTextW(hwnd, buf, n + 2)
        if keyword in buf.value:
            r = RECT()
            user32.GetWindowRect(hwnd, ctypes.byref(r))
            if r.left <= -30000 or r.top <= -30000:
                return True
            if (r.right - r.left) < 300 or (r.bottom - r.top) < 300:
                return True
            result.append((hwnd, r.left, r.top, r.right - r.left, r.bottom - r.top))
        return True

    WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
    user32.EnumWindows(WNDENUMPROC(cb), 0)
    if not result:
        return None
    result.sort(key=lambda t: t[3] * t[4], reverse=True)
    return result[0]


def restore_window(keyword="Sabaki"):
    """把最小化的窗口还原并置前"""
    found = []

    def cb(hwnd, lparam):
        if not user32.IsWindowVisible(hwnd):
            return True
        n = user32.GetWindowTextLengthW(hwnd)
        if n == 0:
            return True
        buf = ctypes.create_unicode_buffer(n + 2)
        user32.GetWindowTextW(hwnd, buf, n + 2)
        if keyword in buf.value and user32.IsIconic(hwnd):
            found.append(hwnd)
        return True

    WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
    user32.EnumWindows(WNDENUMPROC(cb), 0)
    for h in found:
        user32.ShowWindow(h, 9)            # SW_RESTORE
        user32.SetForegroundWindow(h)
    return len(found)


def grab(hwnd, x, y, w, h):
    img = ImageGrab.grab(bbox=(x, y, x + w, y + h), all_screens=True)
    return img.convert("RGB")


def find_board(img):
    """定位棋盘:最大橙色连通块 -> 框内用暗线投影求 19/13/9 条网格线"""
    from scipy import ndimage
    A = np.asarray(img).astype(np.float32)
    R, G, B = A[..., 0], A[..., 1], A[..., 2]
    wood = (R > 150) & (R > B + 60) & (G > 100) & (G < 215) & (B < 170)
    lab, n = ndimage.label(wood)
    if n == 0:
        return None
    sizes = ndimage.sum(wood, lab, range(1, n + 1))
    big = int(np.argmax(sizes)) + 1
    if sizes[big - 1] < 5000:
        return None
    ys, xs = np.where(lab == big)
    x0, x1, y0, y1 = int(xs.min()), int(xs.max()), int(ys.min()), int(ys.max())
    sub = A[y0:y1 + 1, x0:x1 + 1]
    lum = sub.mean(axis=2)
    wood_lum = float(np.median(lum))
    dark = lum < (wood_lum - 45)

    def line_positions(counts):
        if counts.max() <= 0:
            return []
        thr = counts.max() * 0.72
        idx = [i for i, v in enumerate(counts) if v >= thr]
        if not idx:
            return []
        groups, cur = [], [idx[0]]
        for i in idx[1:]:
            if i - cur[-1] <= 2:
                cur.append(i)
            else:
                groups.append(int(round(np.mean(cur))))
                cur = [i]
        groups.append(int(round(np.mean(cur))))
        return groups

    gx = line_positions(dark.sum(axis=0))
    gy = line_positions(dark.sum(axis=1))
    # 校验:必须是 9/13/19 条、行列数一致、间距均匀
    if len(gx) != len(gy) or len(gx) not in (9, 13, 19):
        return None
    for g in (gx, gy):
        d = np.diff(g)
        if len(d) == 0 or d.mean() <= 4:
            return None
        if d.std() / d.mean() > 0.06:
            return None
    return dict(x0=x0, y0=y0, x1=x1, y1=y1, gx=gx, gy=gy, A=sub)


def read_board(size=None, attempts=5):
    win = find_window()
    if not win:
        print(json.dumps({"error": "Sabaki window not found"}, ensure_ascii=False))
        return None
    hwnd, x, y, w, h = win
    b = None
    img = None
    for k in range(attempts):
        img = grab(hwnd, x, y, w, h)
        b = find_board(img)
        if b:
            break
        time.sleep(0.6)
    if not b:
        print(json.dumps({"error": "board not found after %d attempts" % attempts}, ensure_ascii=False))
        return None
    gx, gy = b["gx"], b["gy"]
    if len(gx) < 5 or len(gy) < 5:
        print(json.dumps({"error": "grid not detected", "cols": len(gx), "rows": len(gy)}, ensure_ascii=False))
        return None
    size = min(len(gx), len(gy))
    gx, gy = gx[:size], gy[:size]
    A = b["A"]
    step_x = (gx[-1] - gx[0]) / (size - 1)
    step_y = (gy[-1] - gy[0]) / (size - 1)
    r = max(3, int(min(step_x, step_y) * 0.28))
    lums = A.mean(axis=2)
    sat = A.max(axis=2) - A.min(axis=2)
    grid = []
    for j, cy in enumerate(gy):
        row = []
        for i, cx in enumerate(gx):
            patch = lums[max(cy - r, 0):cy + r + 1, max(cx - r, 0):cx + r + 1]
            psat = sat[max(cy - r, 0):cy + r + 1, max(cx - r, 0):cx + r + 1]
            m, s = patch.mean(), psat.mean()
            if m < 95 and s < 60:
                row.append("B")
            elif m > 205 and s < 45:
                row.append("W")
            else:
                row.append(".")
        grid.append(row)
    out = {
        "size": size,
        "win": [x, y, w, h],
        "board_box": [b["x0"], b["y0"], b["x1"], b["y1"]],
        "grid_x": gx, "grid_y": gy,
        "stones": [[i, j, grid[j][i]] for j in range(size) for i in range(size) if grid[j][i] != "."],
        "move_count": sum(1 for row in grid for c in row if c != "."),
    }
    with open(STATE, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False)
    return out, win, b


def coord_to_pixel(coord, win, board):
    hwnd, wx, wy, ww, wh = win
    b = board
    gx, gy = b["gx"], b["gy"]
    size = len(gx)
    c = coord.strip().upper()
    if c in ("PASS", ""):
        return None
    letter, num = c[0], int(c[1:])
    i = LETTERS.index(letter)
    j = size - num          # 第 size 行(顶部)对应 y 索引 0
    px = wx + b["x0"] + gx[i]
    py = wy + b["y0"] + gy[j]
    return int(px), int(py)


def click(coord):
    """点击指定坐标落子,并校验是否真的落下(最多重试 3 次)"""
    for attempt in range(1, 4):
        win = find_window()
        if not win:
            print("no window"); return False
        hwnd, x, y, w, h = win
        b = None
        for _k in range(6):
            img = grab(hwnd, x, y, w, h)
            b = find_board(img)
            if b:
                break
            time.sleep(0.5)
        if not b:
            print("no board"); return False
        p = coord_to_pixel(coord, win, b)
        if not p:
            print("bad coord"); return False
        # 先激活窗口,等焦点稳定
        user32.SetForegroundWindow(hwnd)
        time.sleep(0.8)
        user32.SetCursorPos(p[0], p[1])
        time.sleep(0.3)
        user32.mouse_event(0x0001, 0, 0, 0, 0)   # 轻微移动,确保 hover 生效
        time.sleep(0.2)
        user32.mouse_event(0x0002, 0, 0, 0, 0)   # LEFTDOWN
        time.sleep(0.08)
        user32.mouse_event(0x0004, 0, 0, 0, 0)   # LEFTUP
        time.sleep(1.0)
        # 校验
        chk = read_board()
        if chk:
            out = chk[0]
            size = out["size"]
            c = coord.strip().upper()
            i = LETTERS.index(c[0]); j = size - int(c[1:])
            got = [s[2] for s in out["stones"] if s[0] == i and s[1] == j]
            if got:
                print("clicked %s at %s (attempt %d, verified)" % (coord, p, attempt))
                return True
            print("attempt %d: %s 未落子,重试" % (attempt, coord))
        else:
            print("attempt %d: 校验读盘失败" % attempt)
    print("FAILED to place %s" % coord)
    return False


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "read"
    if mode == "read":
        r = read_board()
        if r:
            out, win, b = r
            print("size=%d  棋子数=%d" % (out["size"], out["move_count"]))
            print("网格线: x=%d 条, y=%d 条" % (len(b["gx"]), len(b["gy"])))
            for (i, j, c) in out["stones"]:
                print("   %s%s = %s" % (LETTERS[i], out["size"] - j, c))
    elif mode == "click":
        click(sys.argv[2])
    elif mode == "watch":
        last = None
        deadline = time.time() + 3600
        while time.time() < deadline:
            r = read_board()
            if r:
                out = r[0]
                cur = out["move_count"]
                if last is None:
                    last = cur
                elif cur != last:
                    print("盘面变化: %d -> %d 子" % (last, cur))
                    break
            time.sleep(2)
