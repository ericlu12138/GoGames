const fs = require('fs');
const html = fs.readFileSync('F:\\围棋\\games\\selfplay_19\\viewer.html', 'utf8');
const code = html.match(/<script>([\s\S]*)<\/script>/)[1];
const els = {};
function el(id){ if(!els[id]) els[id] = { id, style:{}, textContent:'', innerHTML:'', value:0,
  max:100, getContext:()=>ctx, addEventListener:()=>{}, width:620, height:620 }; return els[id]; }
let arcCount = 0, stoneFills = 0;
const ctx = { fillRect:()=>{}, strokeRect:()=>{}, beginPath:()=>{}, moveTo:()=>{}, lineTo:()=>{},
  stroke:()=>{}, fill:()=>{stoneFills++;}, arc:()=>{arcCount++;}, fillText:()=>{}, clearRect:()=>{},
  measureText:()=>({width:10}), createRadialGradient:()=>({addColorStop:()=>{}}) };
global.ctx = ctx;
global.window = {};
global.document = { getElementById: el, addEventListener: () => {} };
global.setInterval = () => 1; global.clearInterval = () => {};
eval(code);
console.log('arc 调用:', arcCount, '(9 次是星位,其余是棋子)');
console.log('window.__viewerOk =', JSON.stringify(global.window.__viewerOk));
console.log('手数显示 =', els['n'].textContent, els['tot'].textContent, '|', els['last'].textContent);
console.log('滑块 max/value =', els['sl'].max, '/', els['sl'].value);
console.log('波动表行数 =', (els['sw'].innerHTML.match(/<tr>/g)||[]).length);
const drawn = global.window.__viewerOk.drawn;
console.log(drawn === 295 ? '✓ 默认渲染 295 颗子 —— 页面修好了' : '✗ 子数异常: ' + drawn);