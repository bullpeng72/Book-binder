"""Mermaid 노드/엣지 라벨 중 긴 텍스트를 줄바꿈.

다이아몬드(결정) 노드는 라벨 텍스트 폭만큼 도형이 커지는데, 한 줄이 너무
길면 라벨 바운딩 박스가 다이아몬드의 뾰족한 모서리 밖으로 삐져나온다.
`md_to_html()`이 마크다운에서 mermaid 코드 블록을 추출하는 시점에 한 번만
적용해, HTML 사전 렌더링(mermaid_prerender.py)과 PDF 변환(pdf_book.py, 클라
이언트 mermaid.js로 렌더링) 두 경로 모두에서 동일하게 줄바꿈된 결과를 쓴다.

줄바꿈 지점에는 실제 `<br/>` 태그가 아니라 리터럴 `\\n`(백슬래시+n 두 글자)을
심는다 — mermaid 소스는 이후 `<div class="mermaid">...</div>`로 감싸여 다시
HTML로 파싱된다(mermaid_prerender.py의 BeautifulSoup, pdf_book.py의 브라우저
DOM 파싱). 이 시점에 진짜 `<br/>` 태그를 넣으면 실제 `<br>` 엘리먼트로 파싱돼
버리고, 이후 그 텍스트를 다시 꺼낼 때(`get_text()`/`textContent`) 태그가
통째로 사라지면서 양옆 글자가 공백 없이 들러붙는다. 리터럴 `\\n`은 순수
텍스트라 이 왕복을 무사히 통과하고, Mermaid 파서가 따옴표로 감싼 라벨 안의
`\\n`을 자체적으로 줄바꿈으로 처리해준다.
"""

from __future__ import annotations

import re

# 한글/한자/가나 등 폭 2칸짜리 문자 범위. 줄바꿈 폭을 셀 때 ASCII는 1칸,
# 이 범위는 2칸으로 셈해 "체감 길이"에 가깝게 맞춘다.
_WIDE_CHAR_RANGES = (
    (0xAC00, 0xD7A3),  # 한글 음절
    (0x1100, 0x11FF),  # 한글 자모
    (0x3130, 0x318F),  # 한글 호환 자모
    (0x3040, 0x30FF),  # 히라가나/가타카나
    (0x4E00, 0x9FFF),  # CJK 통합 한자
    (0xFF00, 0xFFEF),  # 전각 문자
)

_QUOTED_LABEL_RE = re.compile(r'"([^"\n]+)"')

_BR_TAG_RE = re.compile(r"<br\s*/?>", re.IGNORECASE)

_MAX_LABEL_WIDTH = 18


def _char_width(ch: str) -> int:
    cp = ord(ch)
    return 2 if any(lo <= cp <= hi for lo, hi in _WIDE_CHAR_RANGES) else 1


def _visual_width(s: str) -> int:
    return sum(_char_width(c) for c in s)


def _wrap_label(text: str, max_width: int = _MAX_LABEL_WIDTH) -> str:
    if "\\n" in text or "://" in text:
        return text
    if _visual_width(text) <= max_width:
        return text

    lines: list[str] = []
    current = ""
    current_w = 0

    def flush() -> None:
        nonlocal current, current_w
        if current:
            lines.append(current)
        current, current_w = "", 0

    for word in text.split(" "):
        if not word:
            continue
        word_w = _visual_width(word)
        if word_w > max_width:
            flush()
            chunk, chunk_w = "", 0
            for ch in word:
                cw = _char_width(ch)
                if chunk_w + cw > max_width and chunk:
                    lines.append(chunk)
                    chunk, chunk_w = ch, cw
                else:
                    chunk += ch
                    chunk_w += cw
            current, current_w = chunk, chunk_w
            continue

        sep_w = 1 if current else 0
        if current_w + sep_w + word_w > max_width:
            flush()
            current, current_w = word, word_w
        else:
            current = f"{current} {word}" if current else word
            current_w += sep_w + word_w

    flush()
    return "\\n".join(lines)


def auto_wrap_long_labels(code: str) -> str:
    """따옴표로 감싼 노드/엣지 라벨 중 긴 것을 찾아 줄바꿈을 적용한다.

    Mermaid 문법상 `?`, `(`, `)` 같은 특수문자가 든 라벨은 따옴표로 감싸야만
    파싱되므로(안 그러면 파서가 라벨 중간을 문법 토큰으로 오인해 에러),
    실전에서 긴 한글 라벨은 대부분 이미 따옴표로 감싸져 있다 — 그 부분만
    대상으로 삼는다.

    저자가 직접 써넣은 실제 `<br/>` 태그도 여기서 리터럴 `\\n`으로 정규화한다
    — 그대로 두면 이 `<div class="mermaid">` 텍스트가 이후 HTML로 파싱될 때
    (mermaid_prerender.py의 BeautifulSoup, pdf_book.js의 `textContent`) 진짜
    `<br>` 엘리먼트가 되어 텍스트를 뽑아낼 때 통째로 사라지고, 양옆 글자가
    공백 없이 들러붙는다(모듈 docstring 참고). `\\n`은 순수 텍스트라 이 왕복을
    무사히 통과한다.
    """

    def _sub(m: re.Match) -> str:
        label = _BR_TAG_RE.sub(lambda _m: "\\n", m.group(1))
        return '"' + _wrap_label(label) + '"'

    return _QUOTED_LABEL_RE.sub(_sub, code)
