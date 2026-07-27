"""mermaid_prerender.prerender_mermaid()의 회귀 테스트.

과거엔 CDN mermaid.js를 열람 시점에 항상 불러왔다 — 다이어그램이 하나도
없어도, Playwright 사전 렌더링에 전부 성공해도 매번 3MB 넘는 스크립트를
불러왔다. 다이어그램 없음/사전 렌더링 성공/실패 세 경로 각각에서 "CDN이
여전히 필요한가" 플래그가 올바른지 확인한다.
"""

from unittest import mock

import pytest

from mdbook_binder.mermaid_prerender import prerender_mermaid


def test_no_diagrams_never_needs_cdn():
    html = "<section><p>본문만 있음.</p></section>"
    out, needs_cdn = prerender_mermaid(html)
    assert out == html
    assert needs_cdn is False


def test_prerender_failure_falls_back_to_cdn():
    """Playwright/Chromium이 없어도 빌드 자체는 죽지 않고 CDN 폴백으로 유지돼야 한다."""
    html = '<div class="mermaid">flowchart TD\nA --> B</div>'
    with mock.patch(
        "mdbook_binder.mermaid_prerender._render_svgs",
        side_effect=RuntimeError("Executable doesn't exist"),
    ):
        out, needs_cdn = prerender_mermaid(html)
    assert needs_cdn is True
    assert "flowchart TD" in out


def test_real_render_produces_inline_svg_and_skips_cdn():
    pytest.importorskip("playwright.sync_api")
    html = '<div class="mermaid">flowchart TD\nA --> B</div>'
    out, needs_cdn = prerender_mermaid(html)
    if needs_cdn:
        pytest.skip("Chromium 미설치로 사전 렌더링 불가 — playwright install chromium 필요")
    assert "<svg" in out
    assert 'data-prerendered="true"' in out
    assert "flowchart TD" not in out
