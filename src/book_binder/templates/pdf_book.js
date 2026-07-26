(async () => {
  const ALLOWED = new Set(['python', 'bash', 'shell', 'sh', 'yaml', 'json', 'javascript', 'js', 'html', 'css', 'sql', 'dockerfile']);
  document.querySelectorAll('pre code').forEach(block => {
    const cls = block.className || '';
    const m = cls.match(/language-([a-z0-9_+-]+)/);
    if (m && ALLOWED.has(m[1])) hljs.highlightElement(block);
    else block.classList.add('plain-code');
  });

  // Mermaid 전처리: 노드 라벨 내 리터럴 개행 → <br/>
  document.querySelectorAll('.mermaid').forEach(el => {
    let src = el.textContent;
    let out = '';
    let inQuote = false;
    for (let i = 0; i < src.length; i++) {
      const ch = src[i];
      if (ch === '"') { inQuote = !inQuote; out += ch; }
      else if (ch === '\\' && src[i + 1] === 'n' && inQuote) { out += '<br/>'; i++; }
      else { out += ch; }
    }
    if (out !== src) el.textContent = out;
  });

  mermaid.initialize({
    startOnLoad: false,
    theme: 'default',
    securityLevel: 'loose',
    fontFamily: 'Noto Sans KR, sans-serif',
  });
  try {
    await Promise.race([
      mermaid.run({ querySelector: '.mermaid' }),
      new Promise(resolve => setTimeout(resolve, 15000)),
    ]);
  } catch (e) { console.warn('mermaid.run error:', e); }

  const main = document.getElementById('main') || document.body;
  const availW = main.clientWidth - 48;

  // 테이블 자동 스케일링
  document.querySelectorAll('table').forEach(table => {
    if (table.parentElement.classList.contains('table-scale-wrap')) return;
    const tableW = table.scrollWidth;
    if (tableW <= availW + 2) return;
    const scale = availW / tableW;
    const origH = table.offsetHeight;
    const wrap = document.createElement('div');
    wrap.className = 'table-scale-wrap';
    wrap.style.height = `${Math.ceil(origH * scale)}px`;
    table.parentNode.insertBefore(wrap, table);
    wrap.appendChild(table);
    table.style.transformOrigin = 'top left';
    table.style.transform = `scale(${scale})`;
  });

  // Mermaid SVG 크기 보정
  document.querySelectorAll('.mermaid svg').forEach(svg => {
    svg.style.cssText = '';
    const r = svg.getBoundingClientRect();
    const w = r.width, h = r.height;
    if (w <= 0 || h <= 0) return;
    const scale = w > availW ? availW / w : 1;
    svg.setAttribute('width', Math.ceil(w * scale));
    svg.setAttribute('height', Math.ceil(h * scale));
    svg.removeAttribute('style');
    svg.style.cssText = 'display:block !important; margin:0 auto !important;';
  });

  // 이미지 자동 크기 조정
  document.querySelectorAll('img').forEach(img => {
    if (img.closest('.mermaid-chunk')) return;
    const iw = img.naturalWidth;
    const ih = img.naturalHeight;
    if (iw > 0 && iw > availW) {
      img.setAttribute('width', Math.round(availW));
      img.setAttribute('height', Math.round(ih * availW / iw));
    }
  });

  window.__mermaidDone = true;
})();
