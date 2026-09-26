# -*- coding: utf-8 -*-
"""生成 GoDojo 应用图标(棋盘 + 黑白子),输出多尺寸 .ico"""
import os
from PIL import Image, ImageDraw

S = 1024
OUT = r"F:\围棋\webapp\assets\godogo.ico"
os.makedirs(os.path.dirname(OUT), exist_ok=True)

# 木纹底:上浅下深的竖向渐变
img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
grad = Image.new("RGB", (1, S))
gd = ImageDraw.Draw(grad)
for y in range(S):
    t = y / (S - 1)
    r = int(0xEC + (0xD4 - 0xEC) * t)
    g = int(0xCE + (0xA6 - 0xCE) * t)
    b = int(0x97 + (0x5E - 0x97) * t)
    gd.point((0, y), fill=(r, g, b))
img.paste(grad.resize((S, S)), (0, 0))

# 圆角遮罩
mask = Image.new("L", (S, S), 0)
ImageDraw.Draw(mask).rounded_rectangle([26, 26, S - 26, S - 26], radius=210, fill=255)
img.putalpha(mask)

d = ImageDraw.Draw(img)

# 棋盘格线(5x5)
m0, step, lw = 196, 158, 17
line_c = (0x6B, 0x4A, 0x24, 255)
for k in range(5):
    p = m0 + k * step
    d.line([(m0, p), (m0 + 4 * step, p)], fill=line_c, width=lw)
    d.line([(p, m0), (p, m0 + 4 * step)], fill=line_c, width=lw)


def stone(cx, cy, r, black):
    """带高光的立体棋子"""
    if black:
        d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(0x10, 0x10, 0x10, 255))
        hi = (0x4A, 0x4A, 0x4A, 150)
    else:
        d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(0xFB, 0xFB, 0xFB, 255))
        d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=(0x8E, 0x8E, 0x8E, 255), width=6)
        hi = (0xFF, 0xFF, 0xFF, 240)
    # 高光:偏左上的一小块
    hr = int(r * 0.42)
    hx, hy = int(cx - r * 0.30), int(cy - r * 0.34)
    d.ellipse([hx - hr, hy - hr, hx + hr, hy + hr], fill=hi)


p1 = m0 + 1 * step          # 第 2 条线
p2 = m0 + 3 * step          # 第 4 条线
stone(p1, p1, 132, True)    # 黑子(左上)
stone(p2, p2, 132, False)   # 白子(右下)

sizes = [256, 128, 64, 48, 32, 16]
img.save(OUT, format="ICO", sizes=[(n, n) for n in sizes])
print("saved:", OUT, os.path.getsize(OUT), "bytes")
print("sizes:", sizes)
