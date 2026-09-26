/* GoDojo Web 版 · 前端逻辑
 * 与服务端约定:board 用 grid[i][j] 表示(i = 列, j = 行且 j=0 在最上面),
 * 与服务端 core.Board.g 的下标一致,画布坐标因此是 x = pad + i*cell, y = pad + j*cell。
 */
'use strict';

const L = 'ABCDEFGHJKLMNOPQRST';
const cv = document.getElementById('board');
const ctx = cv.getContext('2d');
const $ = (id) => document.getElementById(id);

let st = null;          // 最新状态快照
let sig = '';           // 状态签名:变了才重绘,避免每 260ms 白刷
let side = 600;         // 画布 CSS 边长
let hover = null;       // 悬停格 {i,j}
let deadNotified = false;

/* ---------------- 通信 ---------------- */

async function get(path) {
  const r = await fetch(path, { cache: 'no-store' });
  return r.json();
}
async function post(path, body) {
  const r = await fetch(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body || {})
  });
  return r.json();
}

function signature(s) {
  return JSON.stringify([
    s.size, s.grid, s.moves.length, s.last_move, s.hint, s.busy,
    s.status, s.coach, s.eval, s.captures, s.game_over, s.engine.ready, s.human
  ]);
}

async function refresh() {
  try {
    const s = await get('/api/state');
    st = s;
    deadNotified = false;
    if (signature(s) !== sig) { sig = signature(s); render(); }
  } catch (e) {
    if (!deadNotified) { toast('与服务端失去连接,重试中…', true); deadNotified = true; }
  }
}

function loop() {
  refresh().finally(() => setTimeout(loop, 260));
}

/* ---------------- 提示条 ---------------- */

let toastTimer = null;
function toast(msg, isErr) {
  const t = $('toast');
  t.textContent = msg;
  t.className = 'show' + (isErr ? ' err' : '');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { t.className = ''; }, isErr ? 4200 : 2400);
}

/* ---------------- 画布尺寸 ---------------- */

function resize() {
  const wrap = $('boardWrap');
  const w = wrap.clientWidth, h = wrap.clientHeight;
  side = Math.max(240, Math.floor(Math.min(w, h)) - 6);
  const dpr = window.devicePixelRatio || 1;
  cv.style.width = side + 'px';
  cv.style.height = side + 'px';
  cv.width = Math.round(side * dpr);
  cv.height = Math.round(side * dpr);
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  drawBoard();
}

function geom() {
  const N = st ? st.size : 19;
  const pad = Math.round(side * 0.048) + 17;
  const cell = (side - pad * 2) / (N - 1);
  return { N, pad, cell };
}

/* ---------------- 棋盘绘制 ---------------- */

const STARS = {
  9: [[2, 2], [6, 2], [4, 4], [2, 6], [6, 6]],
  13: [[3, 3], [9, 3], [6, 6], [3, 9], [9, 9]],
  19: [[3, 3], [9, 3], [15, 3], [3, 9], [9, 9], [15, 9], [3, 15], [9, 15], [15, 15]]
};

function stone(x, y, r, black) {
  ctx.beginPath();
  ctx.arc(x, y, r, 0, Math.PI * 2);
  const g = ctx.createLinearGradient(x - r, y - r, x + r, y + r);
  if (black) { g.addColorStop(0, '#3a3a3a'); g.addColorStop(.45, '#141414'); g.addColorStop(1, '#000'); }
  else { g.addColorStop(0, '#ffffff'); g.addColorStop(.5, '#f2f2f2'); g.addColorStop(1, '#cfcfcf'); }
  ctx.fillStyle = g;
  ctx.fill();
  ctx.strokeStyle = black ? '#000' : '#9a9a9a';
  ctx.lineWidth = 1;
  ctx.stroke();
}

function drawBoard() {
  ctx.clearRect(0, 0, side, side);
  ctx.fillStyle = '#e3b877';
  ctx.fillRect(0, 0, side, side);
  if (!st) return;

  const { N, pad, cell } = geom();
  const a = pad, b = pad + cell * (N - 1);

  // 格线
  ctx.strokeStyle = '#6b4a24';
  ctx.lineWidth = 1;
  ctx.beginPath();
  for (let k = 0; k < N; k++) {
    const p = pad + k * cell;
    ctx.moveTo(a, p); ctx.lineTo(b, p);
    ctx.moveTo(p, a); ctx.lineTo(p, b);
  }
  ctx.stroke();
  ctx.lineWidth = 2.2;
  ctx.strokeRect(a, a, b - a, b - a);

  // 星位
  ctx.fillStyle = '#6b4a24';
  for (const [i, j] of (STARS[N] || [])) {
    ctx.beginPath();
    ctx.arc(pad + i * cell, pad + j * cell, Math.max(2.4, cell * 0.075), 0, Math.PI * 2);
    ctx.fill();
  }

  // 坐标
  ctx.fillStyle = '#6b4a24';
  ctx.font = '12px "Microsoft YaHei",sans-serif';
  ctx.textAlign = 'center';
  ctx.textBaseline = 'middle';
  for (let i = 0; i < N; i++) ctx.fillText(L[i], pad + i * cell, b + cell * 0.6);
  for (let j = 0; j < N; j++) ctx.fillText(String(N - j), a - cell * 0.62, pad + j * cell);

  // 悬停幽灵子
  const myTurn = st.turn === st.human && !st.busy && !st.game_over;
  if (hover && myTurn && st.grid[hover.i][hover.j] === 0) {
    ctx.globalAlpha = 0.32;
    stone(pad + hover.i * cell, pad + hover.j * cell, cell * 0.465, st.human === 'B');
    ctx.globalAlpha = 1;
  }

  // 棋子
  const r = cell * 0.465;
  for (let j = 0; j < N; j++) {
    for (let i = 0; i < N; i++) {
      const v = st.grid[i][j];
      if (!v) continue;
      stone(pad + i * cell, pad + j * cell, r, v === 1);
    }
  }

  // 最近 12 手的手数
  if ($('showNums').checked) {
    const mv = st.moves;
    const from = Math.max(0, mv.length - 12);
    ctx.font = 'bold 11px Consolas,monospace';
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    for (let k = from; k < mv.length; k++) {
      const m = mv[k];
      if (m[1] === 'pass') continue;
      const i = L.indexOf(m[1][0]);
      const j = N - parseInt(m[1].slice(1), 10);
      if (i < 0 || j < 0 || j >= N) continue;
      ctx.fillStyle = (m[0] === 'B') ? '#ffffff' : '#111111';
      ctx.fillText(String(k + 1), pad + i * cell, pad + j * cell);
    }
  }

  // 最后一手:画红圈而不是实心点,免得盖住这一手的手数
  if (st.last_move) {
    const [i, j] = st.last_move;
    ctx.beginPath();
    ctx.arc(pad + i * cell, pad + j * cell, r * 1.08, 0, Math.PI * 2);
    ctx.strokeStyle = '#e53935';
    ctx.lineWidth = Math.max(2, cell * 0.055);
    ctx.stroke();
  }

  // 提示点
  st.hint.forEach((p, k) => {
    const x = pad + p[0] * cell, y = pad + p[1] * cell;
    ctx.beginPath();
    ctx.arc(x, y, r, 0, Math.PI * 2);
    ctx.setLineDash([4, 3]);
    ctx.strokeStyle = '#1b7f3a';
    ctx.lineWidth = 2;
    ctx.stroke();
    ctx.setLineDash([]);
    ctx.fillStyle = '#1b7f3a';
    ctx.font = 'bold 12px "Microsoft YaHei",sans-serif';
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.fillText('ABC'[k] || '', x, y);
  });
}

/* ---------------- 面板渲染 ---------------- */

function render() {
  if (!st) return;
  drawBoard();

  const stEl = $('status');
  stEl.textContent = st.status || '';
  const t = st.status || '';
  if (/❌|失败|出错|非法|超时|不能|没找到/.test(t)) stEl.className = 'status bad';
  else if (/✅|就绪|轮到你|完成/.test(t)) stEl.className = 'status good';
  else stEl.className = 'status';
  $('coach').textContent = st.coach || '';
  $('busyOverlay').classList.toggle('hidden', !st.busy);
  $('busyText').textContent = st.busy ? (st.opponent === 'external' ? '等待外接 AI…' : '引擎思考中…') : '';

  // 胜率条
  const wr = st.eval && st.eval.winrate;
  const fill = $('evalFill');
  if (wr === null || wr === undefined) {
    fill.style.width = '50%';
    fill.style.background = '#4a4a4a';
    $('evalText').textContent = '胜率 --';
  } else {
    fill.style.width = (wr * 100).toFixed(1) + '%';
    fill.style.background = '#23262c';
    $('evalText').textContent =
      `你 ${(wr * 100).toFixed(1)}%   目差 ${st.eval.lead === null ? '--' : (st.eval.lead >= 0 ? '+' : '') + st.eval.lead.toFixed(1)}`;
  }

  // 关键信息行
  // 引擎徽标三态:就绪(绿) / 正在启动或首次调优(橙) / 未就绪(红)
  const eng = st.engine || {};
  const eBadge = eng.ready
    ? '<b style="color:#7fd1a0">就绪</b>'
    : (eng.progress
       ? `<b style="color:#e8b04b" title="${eng.progress}">启动中…</b>`
       : '<b style="color:#ef6a6a">未就绪</b>');
  $('kvRow').innerHTML =
    `<span><b>${st.size} 路</b></span>` +
    `<span>贴目 <b>${st.komi}</b></span>` +
    (st.handicap ? `<span>让 <b>${st.handicap}</b> 子</span>` : '') +
    `<span>你执 <b>${st.human === 'B' ? '黑' : '白'}</b></span>` +
    `<span>强度 <b>${st.visits}</b></span>` +
    `<span>引擎 ${eBadge}</span>`;
  // 首次调优是长任务(5-10 分钟),状态行会一直显示进度,这里不再重复

  // 候选点(统一换算成"你方视角")
  const cs = (st.eval && st.eval.cands) || [];
  const tb = $('cands').querySelector('tbody');
  if (!cs.length) {
    tb.innerHTML = '<tr><td class="dim">—</td></tr>';
  } else {
    const sign = (st.eval.lead !== null && st.eval.lead !== undefined && st.eval.lead < 0) ? -1 : 1;
    tb.innerHTML = cs.slice(0, 5).map((c, k) => {
      const sl = c.scoreLead;
      const mine = (c.move === 'pass') ? 'pass'
        : (sl === null || sl === undefined) ? '--'
          : ((sign > 0 ? sl : -sl) >= 0 ? '+' : '') + (sign > 0 ? sl : -sl).toFixed(1);
      return `<tr><td class="mv">${k === 0 ? '★ ' : '&nbsp;&nbsp;'}${c.move}</td>` +
        `<td class="lead">${mine} 目</td>` +
        `<td class="vs">${c.visits || 0} visits</td></tr>`;
    }).join('');
  }
  $('pv').textContent = (st.eval && st.eval.pv) ? ('主变: ' + st.eval.pv) : '';

  // 对局记录
  $('capInfo').textContent = `提子 你 ${st.captures.human} / AI ${st.captures.ai}`;
  const rows = [];
  for (let k = 0; k < st.moves.length; k += 2) {
    const a = st.moves[k], b = st.moves[k + 1];
    const cell = (m) => m
      ? `<span class="${m[0] === 'B' ? 'bk' : 'wt'}">${m[0] === 'B' ? '黑' : '白'}${m[1]}</span>`
      : '';
    rows.push(`<div><span class="no">${String(k + 1).padStart(3, ' ')}</span>  ${cell(a)}${b ? '  ' + cell(b) : ''}</div>`);
  }
  const ml = $('moveList');
  const atBottom = ml.scrollTop + ml.clientHeight >= ml.scrollHeight - 24;
  ml.innerHTML = rows.join('') || '<span class="dim">尚未落子</span>';
  if (atBottom) ml.scrollTop = ml.scrollHeight;

  // 按钮可用性
  const ready = st.engine.ready;
  const lock = st.busy || !ready || st.game_over;
  $('bUndo').disabled = st.busy || !ready;
  $('bHint').disabled = lock;
  $('bPass').disabled = lock;
  $('bAnalyze').disabled = lock;
  $('bNew').disabled = !ready;
  $('bSave').disabled = st.moves.length === 0;

  // 顶部控件回填(仅在用户没在操作时同步)
  syncControls();
}

let syncing = false;
function syncControls() {
  if (syncing) return;
  syncing = true;
  if ($('fSize').value !== String(st.size)) $('fSize').value = String(st.size);
  if ($('fColor').value !== st.human) $('fColor').value = st.human;
  if ($('fOpp').value !== st.opponent) $('fOpp').value = st.opponent;
  if ($('fHc').value !== String(st.handicap)) $('fHc').value = String(st.handicap);
  if (document.activeElement !== $('fVisits')) {
    $('fVisits').value = String(st.visits);
    $('fVisitsOut').textContent = String(st.visits);
  }
  syncing = false;
}

/* ---------------- 交互 ---------------- */

function hitTest(ev) {
  const rect = cv.getBoundingClientRect();
  const x = ev.clientX - rect.left, y = ev.clientY - rect.top;
  const { N, pad, cell } = geom();
  const i = Math.round((x - pad) / cell), j = Math.round((y - pad) / cell);
  if (i < 0 || i >= N || j < 0 || j >= N) return null;
  if (Math.abs(x - (pad + i * cell)) > cell * 0.5) return null;
  if (Math.abs(y - (pad + j * cell)) > cell * 0.5) return null;
  return { i, j, x, y };
}

cv.addEventListener('click', async (ev) => {
  if (!st) return;
  const h = hitTest(ev);
  if (!h) return;
  const coord = L[h.i] + (st.size - h.j);
  const d = await post('/api/play', { coord });
  if (!d.ok) toast(d.error || '不能下这里', true);
  await refresh();
});

cv.addEventListener('mousemove', (ev) => {
  const h = hitTest(ev);
  const nxt = h ? { i: h.i, j: h.j } : null;
  const same = (!nxt && !hover) || (nxt && hover && nxt.i === hover.i && nxt.j === hover.j);
  if (same) return;
  hover = nxt;
  cv.style.cursor = h ? 'pointer' : 'default';
  drawBoard();
});

cv.addEventListener('mouseleave', () => {
  if (!hover) return;
  hover = null;
  cv.style.cursor = 'default';
  drawBoard();
});

// 顶部控件:改设置即开新局(与原版行为一致)
['fSize', 'fColor', 'fOpp', 'fHc'].forEach((id) => {
  $(id).addEventListener('change', () => newGame());
});
$('fVisits').addEventListener('input', () => {
  $('fVisitsOut').textContent = $('fVisits').value;
});
$('fVisits').addEventListener('change', async () => {
  const v = parseInt($('fVisits').value, 10);
  await post('/api/visits', { visits: v });
  toast('强度已调为 ' + v + ' visits');
});
$('showNums').addEventListener('change', drawBoard);

async function newGame() {
  if (syncing) return;
  const d = await post('/api/new', {
    size: parseInt($('fSize').value, 10),
    human: $('fColor').value,
    opponent: $('fOpp').value,
    handicap: parseInt($('fHc').value, 10),
    visits: parseInt($('fVisits').value, 10)
  });
  if (d.ok) toast('新局开始');
  else toast(d.error || '开局失败', true);
  await refresh();
}

async function action(path, name) {
  const d = await post(path);
  if (!d.ok) toast(d.error || (name + '失败'), true);
  await refresh();
}

$('bNew').onclick = newGame;
$('bUndo').onclick = () => action('/api/undo', '悔棋');
$('bHint').onclick = () => action('/api/hint', '提示');
$('bPass').onclick = () => action('/api/pass', '停一手');
$('bAnalyze').onclick = () => action('/api/analyze', '分析');
$('bResign').onclick = async () => {
  if (!confirm('确定认输?')) return;
  await action('/api/resign', '认输');
};
$('bSave').onclick = async () => {
  const d = await post('/api/save');
  toast(d.path ? ('棋谱已保存: ' + d.path) : '棋谱保存失败', !d.path);
};

// 快捷键
document.addEventListener('keydown', (e) => {
  if (/^(INPUT|SELECT|TEXTAREA)$/.test(document.activeElement.tagName)) return;
  const k = e.key.toLowerCase();
  if (k === 'z' || k === 'u') { e.preventDefault(); action('/api/undo', '悔棋'); }
  else if (k === 'h') action('/api/hint', '提示');
  else if (k === 'p') action('/api/pass', '停一手');
  else if (k === 'a') action('/api/analyze', '分析');
  else if (k === 'n') newGame();
});

/* ---------------- 设置弹窗 ---------------- */

const modal = $('settings');
$('bSettings').onclick = async () => {
  const d = await get('/api/detect');
  const paths = (st && st.engine && st.engine.paths) || {};
  $('sKatago').value = paths.katago || d.katago || '';
  $('sModel').value = paths.model || d.model || '';
  $('sCfg').value = paths.config || d.config || '';
  $('detectNotes').textContent = (d.notes || []).join('\n');
  modal.classList.remove('hidden');
};
$('sClose').onclick = () => modal.classList.add('hidden');
modal.addEventListener('click', (e) => { if (e.target === modal) modal.classList.add('hidden'); });

$('sDetect').onclick = async () => {
  const d = await get('/api/detect');
  $('sKatago').value = d.katago || '';
  $('sModel').value = d.model || '';
  $('sCfg').value = d.config || '';
  $('detectNotes').textContent = (d.notes || []).join('\n');
};
$('sSave').onclick = async () => {
  const d = await post('/api/settings', {
    engine: { katago: $('sKatago').value.trim(), model: $('sModel').value.trim(), config: $('sCfg').value.trim() }
  });
  $('detectNotes').textContent = (d.notes || []).join('\n');
  toast('设置已保存');
};
$('sRestart').onclick = async () => { await post('/api/restart-engine'); toast('正在重启引擎…'); await refresh(); };
$('sKill').onclick = async () => {
  if (!confirm('这会强制结束所有 katago.exe 进程\n(如果有别的 GoDojo 实例正在用引擎,它也会被中断)\n继续?')) return;
  const d = await post('/api/killstale');
  toast(d.ok ? '已清理残留引擎进程' : ('清理失败: ' + (d.msg || '')), !d.ok);
};

/* ---------------- 心跳与退出 ---------------- */

// 每 2 秒报一次心跳(仅用于"页面活着"的辅助判断;真正判断窗口关闭靠系统窗口枚举)
setInterval(function () {
  fetch('/api/ping', { method: 'POST' }).catch(function () { });
}, 2000);

// 窗口关闭时用信标通知后端退出 —— beforeunload 在关窗时一定会触发
window.addEventListener('beforeunload', function () {
  try { navigator.sendBeacon('/api/quit'); } catch (e) { }
});

$('bQuit').onclick = async function () {  if (!confirm('退出 GoDojo?\n当前棋谱会自动保存。')) return;
  try { await post('/api/quit'); } catch (e) { }
  document.body.insertAdjacentHTML('beforeend',
    '<div class="farewell"><b>已退出 GoDojo</b><br>' +
    '<span>窗口即将自动关闭;若没有关掉,请手动关闭</span></div>');
  setTimeout(function () { try { window.close(); } catch (e) { } }, 500);
};

/* ---------------- 启动 ---------------- */

window.addEventListener('resize', resize);
new ResizeObserver(resize).observe($('boardWrap'));
resize();
loop();

// 布局自检:把真实尺寸写进日志,便于排查"棋盘超宽/被裁掉"这类问题
setTimeout(function () {
  const w = $('boardWrap');
  post('/api/diag', {
    innerW: window.innerWidth, innerH: window.innerHeight,
    dpr: window.devicePixelRatio,
    bodyW: document.body.clientWidth, bodyH: document.body.clientHeight,
    layoutW: $('layout').clientWidth, layoutH: $('layout').clientHeight,
    wrapW: w.clientWidth, wrapH: w.clientHeight,
    panelW: $('panel').clientWidth,
    side: side,
    canvasCss: cv.style.width + ' x ' + cv.style.height,
    docScrollW: document.documentElement.scrollWidth,
    docClientW: document.documentElement.clientWidth
  });
}, 2500);
