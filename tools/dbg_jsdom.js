const { JSDOM } = require('D:\\deepseek-harness\\node_modules\\jsdom');
const http = require('http');
http.get('http://127.0.0.1:8123/viewer.html', res => {
  let body = '';
  res.on('data', d => body += d);
  res.on('end', () => {
    const errs = [];
    const dom = new JSDOM(body, {
      runScripts: 'dangerously',
      pretendToBeVisual: true,
      beforeParse(w){
        w.HTMLCanvasElement.prototype.getContext = function(){
          const calls = { arc: 0, fill: 0, fillText: 0 };
          const c = new Proxy({}, { get:(t,k)=>{
            if (k === 'createRadialGradient') return () => ({ addColorStop(){} });
            if (k === 'measureText') return () => ({ width: 10 });
            if (k === 'canvas') return { width:620, height:620 };
            return (...a)=>{ if(k in calls) calls[k]++; };
          }, set:()=>true });
          c.__calls = calls;
          w.__ctx = c;
          return c;
        };
        w.addEventListener('error', e => errs.push('window.onerror: ' + e.message));
      }
    });
    setTimeout(() => {
      const w = dom.window, d = w.document;
      console.log('JS 报错:', errs.length ? errs.join(' | ') : '无');
      console.log('__viewerOk =', JSON.stringify(w.__viewerOk));
      const c = w.__ctx && w.__ctx.__calls;
      console.log('canvas 调用: arc=%s fill=%s fillText=%s', c?c.arc:'?', c?c.fill:'?', c?c.fillText:'?');
      console.log('手数显示:', d.getElementById('n').textContent, d.getElementById('tot').textContent);
      console.log('最后一行:', d.getElementById('last').textContent);
      console.log('滑块:', d.getElementById('sl').max, '/', d.getElementById('sl').value);
      console.log('波动表行数:', (d.getElementById('sw').innerHTML.match(/<tr>/g)||[]).length);
      console.log('canvas 元素尺寸:', d.getElementById('bd').width, 'x', d.getElementById('bd').height);
    }, 1200);
  });
}).on('error', e => console.log('请求失败', e.message));