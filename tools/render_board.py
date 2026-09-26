# -*- coding: utf-8 -*-
"""把棋局渲染成 PNG 图形棋盘(带坐标、手数、候选标记),供新手看。
用法示例:
  python render_board.py --size 9 --moves "b:E5,w:E3" --title "教学局 第1手" \
      --cand "A:E7,B:C3" --out D:\Go\board.png
"""
import argparse, os, sys
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Circle, Rectangle

plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False

LETTERS = "ABCDEFGHJKLMNOPQRST"


def coord_to_xy(c, size):
    """'E5' -> (x, y) 以左下角为 (0,0)"""
    c = c.strip().upper()
    if c in ("PASS", ""):
        return None
    letter = c[0]
    num = int(c[1:])
    x = LETTERS.index(letter)
    y = num - 1
    return x, y


def render(size, moves, title, cands, marks, out):
    fig, ax = plt.subplots(figsize=(6.4, 6.4), dpi=120)
    ax.set_xlim(-1.2, size + 0.2)
    ax.set_ylim(-1.2, size + 0.2)
    ax.set_aspect("equal")
    ax.axis("off")

    # 棋盘底色
    ax.add_patch(Rectangle((-0.5, -0.5), size, size, facecolor="#e9cb8f",
                           edgecolor="#7a5a2a", linewidth=3, zorder=0))
    # 网格
    for i in range(size):
        lw = 1.8 if i in (0, size - 1) else 1.0
        ax.plot([0, size - 1], [i, i], color="#4a3016", lw=lw, zorder=1)
        ax.plot([i, i], [0, size - 1], color="#4a3016", lw=lw, zorder=1)
    # 星位
    stars = {9: [(2, 2), (6, 2), (4, 4), (2, 6), (6, 6)],
             13: [(3, 3), (9, 3), (6, 6), (3, 9), (9, 9)],
             19: [(3, 3), (9, 3), (15, 3), (3, 9), (9, 9), (15, 9), (3, 15), (9, 15), (15, 15)]}.get(size, [])
    for (x, y) in stars:
        ax.plot(x, y, marker="o", ms=4, color="#4a3016", zorder=2)

    # 坐标
    for i in range(size):
        ax.text(i, -0.85, LETTERS[i], ha="center", va="center", fontsize=9, color="#4a3016")
        ax.text(-0.85, i, str(i + 1), ha="center", va="center", fontsize=9, color="#4a3016")

    # 棋子
    r = 0.46
    last = None
    for idx, (color, coord) in enumerate(moves):
        p = coord_to_xy(coord, size)
        if p is None:
            continue
        x, y = p
        fc = "#101010" if color.lower().startswith("b") else "#fafafa"
        ec = "#000000" if color.lower().startswith("b") else "#8a8a8a"
        ax.add_patch(Circle((x, y), r, facecolor=fc, edgecolor=ec, lw=1.2, zorder=3))
        last = (x, y)

    # 候选点标记(字母)
    for i, (label, coord) in enumerate(cands):
        p = coord_to_xy(coord, size)
        if p is None:
            continue
        x, y = p
        ax.add_patch(Circle((x, y), r * 0.95, facecolor="none",
                            edgecolor="#1b7f3a", lw=2.0, linestyle="--", zorder=4))
        ax.text(x, y, label, ha="center", va="center", fontsize=13,
                color="#1b7f3a", fontweight="bold", zorder=5)

    # 其它标记(叉/圈)
    for (kind, coord) in marks:
        p = coord_to_xy(coord, size)
        if p is None:
            continue
        x, y = p
        if kind == "x":
            ax.plot([x - 0.25, x + 0.25], [y - 0.25, y + 0.25], color="#c62828", lw=3, zorder=6)
            ax.plot([x - 0.25, x + 0.25], [y + 0.25, y - 0.25], color="#c62828", lw=3, zorder=6)
        elif kind == "dot":
            ax.plot(x, y, marker="o", ms=9, color="#1565c0", zorder=6)

    # 最后一手小红点
    if last:
        ax.plot(last[0], last[1], marker="o", ms=4, color="#e53935", zorder=7)

    if title:
        ax.set_title(title, fontsize=12, pad=10)

    fig.tight_layout()
    fig.savefig(out, facecolor="white", bbox_inches="tight")
    plt.close(fig)
    print("saved", out)


def parse_moves(s):
    out = []
    for part in s.split(","):
        part = part.strip()
        if not part:
            continue
        if ":" in part:
            c, mv = part.split(":", 1)
        else:
            c, mv = "b", part
        out.append((c.strip(), mv.strip()))
    return out


def parse_cands(s):
    out = []
    for part in s.split(","):
        part = part.strip()
        if not part:
            continue
        if ":" in part:
            l, mv = part.split(":", 1)
            out.append((l.strip(), mv.strip()))
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--size", type=int, default=9)
    ap.add_argument("--moves", default="")
    ap.add_argument("--cand", default="")
    ap.add_argument("--marks", default="")      # 形如 x:D4,dot:Q16
    ap.add_argument("--title", default="")
    ap.add_argument("--out", default=r"D:\Go\board.png")
    a = ap.parse_args()
    marks = []
    for part in a.marks.split(","):
        part = part.strip()
        if ":" in part:
            k, mv = part.split(":", 1)
            marks.append((k.strip(), mv.strip()))
    render(a.size, parse_moves(a.moves), a.title, parse_cands(a.cand), marks, a.out)
