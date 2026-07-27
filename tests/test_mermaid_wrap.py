"""mermaid_wrap.auto_wrap_long_labels()의 회귀 테스트."""

from mdbook_binder.mermaid_wrap import auto_wrap_long_labels
from mdbook_binder.render import md_to_html, tip_start_pattern


def test_short_label_untouched():
    code = 'graph TD\nA{"짧은 질문"} --> B["foo"]'
    assert auto_wrap_long_labels(code) == code


def test_long_korean_label_gets_br():
    code = 'graph TD\nA{"이 함수가 부작용을일으키는가? (D.1 질문 5)"} --> B["foo"]'
    out = auto_wrap_long_labels(code)
    assert "\\n" in out
    assert 'B["foo"]' in out  # 짧은 라벨은 그대로


def test_no_space_run_hard_splits():
    code = 'graph TD\nA{"' + "가" * 40 + '"}'
    out = auto_wrap_long_labels(code)
    assert "\\n" in out
    # 줄바꿈 태그를 빼면 원래 글자 수가 보존돼야 한다
    assert out.replace("\\n", "").count("가") == 40


def test_existing_br_tag_normalized_to_backslash_n():
    # 저자가 직접 써넣은 <br/>은 그대로 두면 안 된다 — div.get_text()/textContent가
    # 실제 <br> 엘리먼트를 통째로 삼켜버려 양옆 글자가 공백 없이 들러붙는다.
    code = 'graph TD\nA{"이미<br/>줄바꿈됨 아주 아주 아주 긴 라벨입니다"} --> B'
    out = auto_wrap_long_labels(code)
    assert "<br" not in out.lower()
    assert "\\n" in out


def test_already_backslash_n_wrapped_label_untouched():
    code = 'graph TD\nA{"이미\\n줄바꿈됨 아주 아주 아주 긴 라벨입니다"} --> B'
    assert auto_wrap_long_labels(code) == code


def test_url_label_untouched():
    code = 'graph TD\nA["https://example.com/very/long/path/that/exceeds/threshold"]'
    assert auto_wrap_long_labels(code) == code


def test_md_to_html_wraps_mermaid_source():
    md = (
        "# Title\n\n"
        "```mermaid\n"
        'graph TD\nA{"이 함수가 부작용을일으키는가? (D.1 질문 5)"} --> B["foo"]\n'
        "```\n"
    )
    out = md_to_html(md, tip_start_pattern([]))
    assert "\\n" in out
    assert 'class="mermaid"' in out
