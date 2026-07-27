// CDN(mermaid.js/highlight.js)이 막히거나 로드에 실패해도 이 스크립트의 나머지
// 부분(검색·TOC 활성화 하이라이트)이 죽지 않도록 전역 참조를 전부 방어적으로 감싼다
// — 예전엔 톱레벨 mermaid.initialize()가 무방비로 던져서, mermaid가 로드되지
// 않으면 이 스크립트 블록 전체(아래 DOMContentLoaded 등록까지)가 실행되지
// 않았다. 사전 렌더링된(data-prerendered) 다이어그램은 다시 렌더링하지 않는다.
if (typeof mermaid !== 'undefined') {
  try {
    mermaid.initialize({ startOnLoad: false, theme: 'default', securityLevel: 'loose', fontFamily: 'Noto Sans KR, sans-serif' });
    (document.fonts && document.fonts.ready ? document.fonts.ready : Promise.resolve()).then(function () {
      try {
        var runResult = mermaid.run({ querySelector: '.mermaid:not([data-prerendered])' });
        if (runResult && typeof runResult.catch === 'function') {
          runResult.catch(function (e) { console.warn('mermaid.run failed:', e); });
        }
      } catch (e) { console.warn('mermaid.run failed:', e); }
    });
  } catch (e) { console.warn('mermaid.initialize failed:', e); }
}

document.addEventListener('DOMContentLoaded', function () {
  const ALLOWED = new Set(['python', 'bash', 'shell', 'sh', 'yaml', 'json', 'javascript', 'js', 'html', 'css', 'sql']);
  document.querySelectorAll('pre code').forEach(block => {
    const cls = block.className || '';
    const m = cls.match(/language-([a-z0-9_+-]+)/);
    if (m && ALLOWED.has(m[1]) && typeof hljs !== 'undefined') {
      try { hljs.highlightElement(block); } catch (e) { block.classList.add('plain-code'); }
    } else {
      block.classList.add('plain-code');
    }
  });

  const sections = document.querySelectorAll('.chapter-section[id]');
  const tocLinks = document.querySelectorAll('#toc a[href^="#"]');
  const observer = new IntersectionObserver(entries => {
    entries.forEach(e => {
      if (e.isIntersecting) {
        tocLinks.forEach(a => a.classList.toggle('active', a.getAttribute('href') === '#' + e.target.id));
      }
    });
  }, { rootMargin: '-10% 0px -80% 0px' });
  sections.forEach(s => observer.observe(s));
});

/* ── In-page Search ──────────────────────────────────────────────────────── */
(function () {
  var box = document.getElementById('search-box');
  var count = document.getElementById('search-count');
  var bPrev = document.getElementById('search-prev');
  var bNext = document.getElementById('search-next');
  var main = document.getElementById('main');
  if (!box || !main) return;

  var hits = [], cur = -1, timer;

  function clearMarks() {
    main.querySelectorAll('mark.search-hit').forEach(function (m) {
      m.parentNode.replaceChild(document.createTextNode(m.textContent), m);
    });
    main.normalize();
    hits = []; cur = -1;
  }

  function applySearch(term) {
    clearMarks();
    if (!term) { count.textContent = ''; bPrev.disabled = bNext.disabled = true; return; }
    var lterm = term.toLowerCase();
    var tlen = term.length;
    var walker = document.createTreeWalker(
      main, NodeFilter.SHOW_TEXT,
      {
        acceptNode: function (node) {
          var el = node.parentElement;
          if (!el) return NodeFilter.FILTER_REJECT;
          if (el.closest('pre, code, .mermaid, script, style, mark')) return NodeFilter.FILTER_REJECT;
          return node.nodeValue.trim() ? NodeFilter.FILTER_ACCEPT : NodeFilter.FILTER_SKIP;
        }
      }
    );
    var nodes = [];
    while (walker.nextNode()) nodes.push(walker.currentNode);
    nodes.forEach(function (node) {
      var val = node.nodeValue;
      var lval = val.toLowerCase();
      if (lval.indexOf(lterm) === -1) return;
      var frag = document.createDocumentFragment();
      var last = 0, idx;
      while ((idx = lval.indexOf(lterm, last)) !== -1) {
        if (idx > last) frag.appendChild(document.createTextNode(val.slice(last, idx)));
        var mark = document.createElement('mark');
        mark.className = 'search-hit';
        mark.textContent = val.slice(idx, idx + tlen);
        frag.appendChild(mark);
        hits.push(mark);
        last = idx + tlen;
      }
      if (last < val.length) frag.appendChild(document.createTextNode(val.slice(last)));
      node.parentNode.replaceChild(frag, node);
    });
    if (hits.length) {
      cur = 0; setCurrent();
      count.textContent = '__PLACEHOLDER_HITS_FOUND__'.replace('{n}', hits.length);
    } else {
      count.textContent = '__PLACEHOLDER_NO_MATCH__';
    }
    bPrev.disabled = bNext.disabled = hits.length < 2;
  }

  function setCurrent() {
    hits.forEach(function (m, i) { m.classList.toggle('current', i === cur); });
    if (hits[cur]) hits[cur].scrollIntoView({ behavior: 'smooth', block: 'center' });
    if (hits.length > 1) {
      count.textContent = '__PLACEHOLDER_OF__'.replace('{cur}', cur + 1).replace('{total}', hits.length);
    }
  }

  box.addEventListener('input', function () {
    clearTimeout(timer);
    timer = setTimeout(function () { applySearch(box.value.trim()); }, 250);
  });
  box.addEventListener('keydown', function (e) {
    if (e.key === 'Enter') { e.preventDefault(); if (hits.length) { cur = (cur + 1) % hits.length; setCurrent(); } }
    if (e.key === 'Escape') { box.value = ''; clearMarks(); count.textContent = ''; bPrev.disabled = bNext.disabled = true; box.blur(); }
  });
  bNext.addEventListener('click', function () { if (hits.length) { cur = (cur + 1) % hits.length; setCurrent(); } });
  bPrev.addEventListener('click', function () { if (hits.length) { cur = (cur - 1 + hits.length) % hits.length; setCurrent(); } });
  document.addEventListener('keydown', function (e) {
    if (e.key === '/' && document.activeElement.tagName !== 'INPUT' && document.activeElement.tagName !== 'TEXTAREA') {
      e.preventDefault(); box.focus(); box.select();
    }
  });
})();
