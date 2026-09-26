# -*- coding: utf-8 -*-
"""把棋谱生成为单文件 HTML 图形页面(默认显示终局,含提子处理,可交互回放)。

要点:提子必须真的把子从盘上拿走 —— 早期版本只是叠加,提子后的空点会残留对方的子。
这里在生成阶段就把每一手的完整盘面(含提子)算好,页面只负责显示快照。

用法: python -u make_viewer.py [session目录] [标题]
"""
import json, os, sys

S = sys.argv[1] if len(sys.argv) > 1 else r"F:\围棋\games\selfplay_19"
TITLE = sys.argv[2] if len(sys.argv) > 2 else "KataGo 自战 · 19 路"
N = 19
L = "ABCDEFGHJKLMNOPQRST"
NB = ((1, 0), (-1, 0), (0, 1), (0, -1))


def compute_snapshots(moves, size=19):
    """逐步推进,处理提子,返回每一手之后的盘面快照 + 提子数。"""
    board = [[0] * size for _ in range(size)]     # 0 空 / 1 黑 / 2 白
    snaps = []
    cap_b = cap_w = 0
    for m in moves:
        c = m["coord"].upper()
        if c in ("PASS", "RESIGN"):
            snaps.append([row[:] for row in board])
            continue
        x, y = L.index(c[0]), int(c[1:]) - 1
        me = 1 if m["color"] == "b" else 2
        opp = 3 - me
        board[y][x] = me
        for dx, dy in NB:                          # 检查四个方向相邻的对方棋块
            nx, ny = x + dx, y + dy
            if not (0 <= nx < size and 0 <= ny < size) or board[ny][nx] != opp:
                continue
            seen, stack, libs = {(nx, ny)}, [(nx, ny)], 0
            while stack:
                cx, cy = stack.pop()
                for ax, ay in NB:
                    ux, uy = cx + ax, cy + ay
                    if not (0 <= ux < size and 0 <= uy < size):
                        continue
                    v = board[uy][ux]
                    if v == 0:
                        libs += 1
                    elif v == opp and (ux, uy) not in seen:
                        seen.add((ux, uy)); stack.append((ux, uy))
            if libs == 0:                          # 无气 -> 提掉
                for px, py in seen:
                    board[py][px] = 0
                if opp == 1: cap_b += len(seen)
                else: cap_w += len(seen)
        snaps.append([row[:] for row in board])
    return snaps, cap_b, cap_w


d = json.load(open(os.path.join(S, "moves.json"), encoding="utf-8"))
moves = [m for m in d["moves"] if m["coord"].upper() not in ("PASS", "RESIGN")]
seq = [{"c": m["color"], "p": m["coord"]} for m in moves]
snaps, cap_b, cap_w = compute_snapshots(moves, N)
final = snaps[-1]
on_b = sum(r.count(1) for r in final)
on_w = sum(r.count(2) for r in final)
empty = N * N - on_b - on_w
meta = {"komi": d["komi"], "score": d.get("final_score", ""), "size": N,
        "total": len(seq), "max_time": d.get("max_time", "?"),
        "cap_b": cap_b, "cap_w": cap_w, "on_b": on_b, "on_w": on_w, "empty": empty}
swings = []
try:
    ec = json.load(open(os.path.join(S, "eval_curve.json"), encoding="utf-8"))
    swings = ec.get("biggest_swings", [])[:8]
except Exception:
    pass

TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<title>__TITLE__</title>
<style>
 body{margin:0;background:#14161a;color:#e8e6e3;font-family:"Microsoft YaHei",system-ui,sans-serif;
      display:flex;justify-content:center;padding:18px}
 .wrap{display:flex;gap:22px;align-items:flex-start;flex-wrap:wrap;justify-content:center}
 canvas{background:#e3b877;border-radius:6px;box-shadow:0 6px 26px rgba(0,0,0,.55)}
 .panel{width:350px}
 h1{font-size:19px;margin:0 0 4px}
 .sub{color:#9aa4b2;font-size:13px;margin-bottom:14px;line-height:1.6}
 .card{background:#1d2026;border:1px solid #2b3038;border-radius:8px;padding:12px 14px;margin-bottom:12px}
 .big{font-size:26px;font-variant-numeric:tabular-nums}
 .row{display:flex;gap:8px;align-items:center;margin-top:8px;flex-wrap:wrap}
 button{background:#2a2f37;color:#e8e6e3;border:1px solid #3a4048;border-radius:6px;
        padding:6px 11px;cursor:pointer;font-size:13px}
 button:hover{background:#343a44}
 input[type=range]{width:100%}
 .k{color:#9aa4b2;font-size:12px}
 .key{color:#7fd1a0}
 .stat{display:flex;gap:14px;font-size:12.5px;color:#c9d1d9;margin-top:6px;flex-wrap:wrap}
 table{width:100%;border-collapse:collapse;font-size:12.5px}
 td{padding:3px 2px;color:#c9d1d9}
 td.n{color:#9aa4b2;width:92px}
 .hint{color:#7fd1a0;font-size:12px;margin-top:6px}
</style></head><body>
<div class="wrap">
  <canvas id="bd" width="620" height="620"></canvas>
  <div class="panel">
    <h1>__TITLE__</h1>
    <div class="sub" id="meta"></div>
    <div class="card">
      <div class="k">当前手数</div>
      <div class="big"><span id="n">0</span> <span style="font-size:14px;color:#9aa4b2" id="tot"></span></div>
      <div class="k" id="last">—</div>
      <div class="stat" id="live"></div>
      <input type="range" id="sl" min="0" max="100" value="100">
      <div class="row">
        <button onclick="go(0)">⏮ 开头</button>
        <button onclick="step(-1)">◀ 上一手</button>
        <button onclick="step(1)">下一手 ▶</button>
        <button onclick="go(TOTAL)">末尾 ⏭</button>
      </div>
      <div class="row"><button onclick="auto()" id="ab">▶ 自动播放</button>
        <span class="k">← → 逐手 · Home/End 首末 · 空格播放</span></div>
      <div class="hint">本页已正确处理提子(被提的子会真正消失);打开时显示终局。</div>
    </div>
    <div class="card">
      <div class="k" style="margin-bottom:6px">形势波动最大的区段(赛后分析,白方视角)</div>
      <table id="sw"></table>
    </div>
  </div>
</div>
<script>
const MOVES = __MOVES__;
const SNAPS = __SNAPS__;
const META = __META__;
const SWINGS = __SWINGS__;
const TOTAL = MOVES.length;
const L = "ABCDEFGHJKLMNOPQRST";
const N = META.size, PAD = 34, CELL = (620 - PAD*2) / (N - 1), R = CELL*0.47;
const cv = document.getElementById('bd'), ctx = cv.getContext('2d');
let cur = TOTAL, timer = null;

document.getElementById('meta').textContent =
  `贴目 ${META.komi} · 终局 ${META.score} · 共 ${TOTAL} 手(不含 pass) · 每手 ${META.max_time} 秒`;
document.getElementById('tot').textContent = "/ " + TOTAL;
document.getElementById('sl').max = TOTAL;
document.getElementById('sl').value = TOTAL;

function px(i){ return PAD + i*CELL; }
function statsFor(k){
  const b = (k > 0) ? SNAPS[k-1] : null;
  let nb = 0, nw = 0;
  if (b) for (let r=0;r<N;r++) for (let c=0;c<N;c++){
    if (b[r][c]===1) nb++; else if (b[r][c]===2) nw++;
  }
  return {nb: nb, nw: nw};
}
function draw(){
  ctx.fillStyle = "#e3b877"; ctx.fillRect(0,0,620,620);
  ctx.strokeStyle = "#5a401f"; ctx.lineWidth = 1;
  for (let i=0;i<N;i++){
    ctx.beginPath(); ctx.moveTo(px(0), px(i)); ctx.lineTo(px(N-1), px(i)); ctx.stroke();
    ctx.beginPath(); ctx.moveTo(px(i), px(0)); ctx.lineTo(px(i), px(N-1)); ctx.stroke();
  }
  ctx.lineWidth = 2.4; ctx.strokeStyle = "#5a401f";
  ctx.strokeRect(px(0), px(0), px(N-1)-px(0), px(N-1)-px(0));
  ctx.fillStyle = "#5a401f";
  for (const s of [[3,3],[9,3],[15,3],[3,9],[9,9],[15,9],[3,15],[9,15],[15,15]]){
    ctx.beginPath(); ctx.arc(px(s[0]),px(s[1]),3.4,0,7); ctx.fill();
  }
  ctx.fillStyle = "#4a3417"; ctx.font = "12px sans-serif";
  ctx.textAlign="center"; ctx.textBaseline="middle";
  for (let i=0;i<N;i++){ ctx.fillText(L[i], px(i), 14); ctx.fillText(String(N-i), 14, px(i)); }

  const board = (cur > 0) ? SNAPS[cur-1] : null;
  let drawn = 0, nb = 0, nw = 0;
  if (board){
    for (let r=0;r<N;r++) for (let c=0;c<N;c++){
      const v = board[r][c];
      if (!v) continue;
      ctx.beginPath(); ctx.arc(px(c), px(r), R, 0, 7);
      ctx.fillStyle = (v===1) ? "#111111" : "#f7f7f7"; ctx.fill();
      ctx.strokeStyle = (v===1) ? "#000000" : "#8a8a8a"; ctx.lineWidth = 1; ctx.stroke();
      drawn++; if (v===1) nb++; else nw++;
    }
  }
  if (cur>0){
    const m = MOVES[cur-1], x = L.indexOf(m.p[0]), y = N - parseInt(m.p.slice(1));
    if (x>=0 && x<N && y>=0 && y<N){
      ctx.beginPath(); ctx.arc(px(x), px(y), R*0.28, 0, 7);
      ctx.fillStyle = (m.c==='b') ? "#ff5a52" : "#d81b1b"; ctx.fill();
    }
  }
  ctx.font = "bold 11px sans-serif";
  const from = Math.max(0, cur-12);
  for (let k=from;k<cur;k++){
    const m = MOVES[k], x = L.indexOf(m.p[0]), y = N - parseInt(m.p.slice(1));
    if (x<0||x>=N||y<0||y>=N) continue;
    ctx.fillStyle = (m.c==='b') ? "#ffffff" : "#111111";
    ctx.fillText(String(k+1), px(x), px(y));
  }
  document.getElementById('n').textContent = cur;
  document.getElementById('last').textContent = cur>0
    ? `第 ${cur} 手:${MOVES[cur-1].c==='b'?'黑':'白'} ${MOVES[cur-1].p}`
    : "开局前(空盘)";
  document.getElementById('live').textContent =
    `盘上 黑${nb} + 白${nw} = ${nb+nw} 子 · 空点 ${N*N-nb-nw}`;
  return drawn;
}
function go(v){ cur = Math.max(0, Math.min(TOTAL, v));
  document.getElementById('sl').value = cur; draw(); }
function step(d){ go(cur+d); }
document.getElementById('sl').oninput = function(e){ go(parseInt(e.target.value)); };
function auto(){
  const b = document.getElementById('ab');
  if (timer){ clearInterval(timer); timer=null; b.textContent="▶ 自动播放"; return; }
  b.textContent="⏸ 暂停";
  timer = setInterval(function(){ if (cur>=TOTAL){ auto(); return; } step(1); }, 220);
}
document.addEventListener('keydown', function(e){
  if (e.key==='ArrowLeft') step(-1);
  else if (e.key==='ArrowRight') step(1);
  else if (e.key==='Home') go(0);
  else if (e.key==='End') go(TOTAL);
  else if (e.key===' '){ e.preventDefault(); auto(); }
});
document.getElementById('sw').innerHTML = SWINGS.map(function(s){
  return '<tr><td class="n">第 '+s.from+'→'+s.to+' 手</td><td class="'+(s.delta>0?'key':'')+'">'
       + (s.delta>0?'▲ 白 +':'▼ 白 ') + s.delta.toFixed(1) + ' 目</td></tr>';
}).join('') || '<tr><td class="k">(本局暂无波动分析数据)</td></tr>';
const _drawn = draw();
window.__viewerOk = { drawn: _drawn, cur: cur, total: TOTAL,
  captB: META.cap_b, captW: META.cap_w, onB: META.on_b, onW: META.on_w };
</script></body></html>
"""

html = (TEMPLATE
        .replace("__TITLE__", TITLE)
        .replace("__MOVES__", json.dumps(seq))
        .replace("__SNAPS__", json.dumps(snaps))
        .replace("__META__", json.dumps(meta))
        .replace("__SWINGS__", json.dumps(swings)))
out = os.path.join(S, "viewer.html")
with open(out, "w", encoding="utf-8", newline="\n") as f:
    f.write(html)
left = [p for p in ("__MOVES__", "__SNAPS__", "__META__", "__SWINGS__", "__TITLE__") if p in html]
print("saved %s | %d bytes | 手数 %d | 黑被提 %d 白被提 %d | 终局盘上 黑%d+白%d=%d, 空点 %d | 占位符残留 %s"
      % (out, len(html), len(seq), cap_b, cap_w, on_b, on_w, on_b+on_w, empty, left if left else "无"))