"""Mermaid 다이어그램을 빌드 시점에 정적 SVG로 사전 렌더링.

HTML 도서를 열 때마다 CDN의 mermaid.js에 의존하지 않도록, 가능하면 빌드
시점에 Playwright/Chromium으로 각 다이어그램을 SVG로 렌더링해 그 결과를
그대로 삽입한다. 로컬에 번들된 templates/vendor/mermaid.min.js만 쓰므로
빌드 자체도 네트워크 접속 없이 동작한다.

Playwright가 설치돼 있지 않거나 Chromium 실행에 실패하면(선택 설치인
`[pdf]` extra 미설치 등) 조용히 원본을 유지해, 열람 시 CDN mermaid.js로
렌더링하는 기존 방식으로 폴백한다 — 관대한 파싱 원칙: 사전 렌더링이
안 된다고 HTML 빌드 자체가 실패해서는 안 된다.
"""

from __future__ import annotations

from pathlib import Path

from bs4 import BeautifulSoup

_VENDOR_DIR = Path(__file__).parent / "templates" / "vendor"

_RENDER_JS = """async (codes) => {
    mermaid.initialize({ startOnLoad: false, theme: 'default', securityLevel: 'loose' });
    const out = [];
    for (let i = 0; i < codes.length; i++) {
        try {
            const { svg } = await mermaid.render('mmd_' + i, codes[i]);
            out.push(svg);
        } catch (e) {
            out.push(null);
        }
    }
    return out;
}"""


def prerender_mermaid(sections_html: str) -> tuple[str, bool]:
    """`.mermaid` div의 원본 소스를 렌더링된 `<svg>`로 치환한다.

    반환값의 두 번째 요소는 "열람 시 CDN mermaid.js가 여전히 필요한가"이다
    — 사전 렌더링이 전부 성공하면 False(CDN 스크립트 태그 자체를 생략해도
    됨), 다이어그램이 아예 없어도 False, 일부라도 실패/폴백하면 True.
    """
    soup = BeautifulSoup(sections_html, "html.parser")
    mermaid_divs = soup.find_all("div", class_="mermaid")
    if not mermaid_divs:
        return sections_html, False

    codes = [d.get_text() for d in mermaid_divs]
    try:
        svgs = _render_svgs(codes)
    except Exception as exc:
        print(f"  ⚠️  Mermaid 사전 렌더링 불가({exc}) — 열람 시 CDN mermaid.js로 렌더링됩니다")
        return sections_html, True

    needs_cdn = False
    for div, svg in zip(mermaid_divs, svgs):
        if not svg:
            needs_cdn = True
            continue
        div.clear()
        div["data-prerendered"] = "true"
        div.append(BeautifulSoup(svg, "html.parser"))

    return str(soup), needs_cdn


def _render_svgs(codes: list[str]) -> list[str | None]:
    from playwright.sync_api import sync_playwright

    mermaid_js = (_VENDOR_DIR / "mermaid.min.js").read_text(encoding="utf-8")
    page_html = (
        '<!DOCTYPE html><html><head><meta charset="utf-8">'
        f"<script>{mermaid_js}</script></head><body></body></html>"
    )

    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        try:
            page = browser.new_page()
            page.set_content(page_html, wait_until="load")
            return page.evaluate(_RENDER_JS, codes)
        finally:
            browser.close()
