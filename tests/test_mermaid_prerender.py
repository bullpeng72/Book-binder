"""mermaid_prerender.prerender_mermaid()의 회귀 테스트.

과거엔 CDN mermaid.js를 열람 시점에 항상 불러왔다 — 다이어그램이 하나도
없어도, Playwright 사전 렌더링에 전부 성공해도 매번 3MB 넘는 스크립트를
불러왔다. 다이어그램 없음/사전 렌더링 성공/실패 세 경로 각각에서 "CDN이
여전히 필요한가" 플래그가 올바른지 확인한다.
"""

from unittest import mock

import pytest

from mdbook_binder.mermaid_prerender import _summarize_exc, prerender_mermaid


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


def test_summarize_exc_collapses_playwright_install_banner_to_one_line():
    """Playwright의 "브라우저 미설치" 예외는 안내용 ASCII 박스가 딸린 여러 줄
    메시지다 — 그대로 경고 한 줄에 끼워 넣으면 뒤 문장이 박스 마지막 줄에
    이어붙어 버리므로, 설치 안내 한 줄로 바꿔치기됐는지 확인한다."""
    exc = RuntimeError(
        "BrowserType.launch: Executable doesn't exist at /some/cache/chrome-headless-shell\n"
        "╔════════════════════════════════════════════════════════════╗\n"
        "║ Looks like Playwright was just installed or updated.       ║\n"
        "╚════════════════════════════════════════════════════════════╝"
    )
    summary = _summarize_exc(exc)
    assert "\n" not in summary
    assert "playwright install chromium" in summary


def test_summarize_exc_keeps_only_first_line_of_other_errors():
    exc = RuntimeError("Timeout 30000ms exceeded.\nsome extra multi-line detail\nyet more")
    summary = _summarize_exc(exc)
    assert summary == "Timeout 30000ms exceeded."


def test_summarize_exc_falls_back_to_type_name_for_empty_message():
    assert _summarize_exc(RuntimeError()) == "RuntimeError"
