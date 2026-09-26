const { JSDOM } = require('D:\\deepseek-harness\\node_modules\\jsdom');
const fs = require('fs');
const html = fs.readFileSync('F:\\围棋\\games\\maxsp_g1\\viewer.html', 'utf8');
const errs = [];
const dom = new JSDOM(html, { runScripts: 'dangerously', pretendToBeVisual: true,
  beforeParse(w){
    w.HTMLCanvasElement.prototype.getContext = function(){
      return new Proxy({}, { get:(t,k)=>{
        if (k === 'createRadialGradient') return () => ({ addColorStop(){} });
        if (k === 'measureText') return () => ({ width: 10 });
        return () => {};
      }, set:()=>true });
    };
    w.addEventListener('error', e => errs.push(e.message));
  }});
setTimeout(() => {
  const w = dom.window, d = w.document;
  console.log('JS 错误:', errs.length ? errs.join(' | ') : '无');
  const o = w.__viewerOk;
  console.log('viewerOk:', JSON.stringify(o));
  console.log('手数显示:', d.getElementById('n').textContent, d.getElementById('tot').textContent);
  console.log('实时统计:', d.getElementById('live').textContent);
  console.log('最后一行:', d.getElementById('last').textContent);
  const ok = (o.onB === 119 && o.onW === 121 && o.captB === 63 && o.captW === 66);
  console.log(ok ? '✓ 终局盘面与提子数完全正确(黑119/白121, 黑被提63/白被提66)' : '✗ 数据不符');
}, 1500);