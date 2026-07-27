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

  try { await document.fonts.ready; } catch (e) { /* ignore */ }

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
  // Mermaid는 svg에 width="100%" 속성과 함께 style="max-width: Npx"(자연 크기)를
  // 주입하는데, pdf_override.css의 ".mermaid svg { max-width:100% !important }"가
  // !important로 그 인라인 max-width를 덮어써 버린다. 그 결과 getBoundingClientRect()
  // 로 측정하면 width:100% 속성이 그대로 적용되어 항상 컨테이너 전체 폭으로 늘어난
  // 크기가 나오고, 그 늘어난 폭 기준으로 종횡비를 유지한 채 height도 함께 부풀어
  // (특히 세로로 긴 다이어그램에서 수 배 확대) 여러 페이지에 걸쳐 표시되는 문제가
  // 있었다. CSS 간섭을 받지 않는 viewBox(자연 좌표계 = 자연 px 크기)에서 폭·높이를
  // 읽어, 그 폭이 availW를 초과할 때만 축소한다(자연 크기가 이미 작으면 그대로 유지
  // — 강제로 확대하지 않음).
  document.querySelectorAll('.mermaid svg').forEach(svg => {
    const vb = (svg.getAttribute('viewBox') || '').trim().split(/\s+/).map(Number);
    let w, h;
    if (vb.length === 4 && vb[2] > 0 && vb[3] > 0) {
      w = vb[2]; h = vb[3];
    } else {
      const r = svg.getBoundingClientRect();
      w = r.width; h = r.height;
    }
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
