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

_SUBGRAPH_LINE_RE = re.compile(r"^\s*subgraph\b")

_MAX_LABEL_WIDTH = 18

# 공백 없는 긴 "단어"(식별자·경로 등)를 접을 때 우선적으로 끊을 자연 경계.
# `/`, `_`, `.`, `-` 뒤나 camelCase 전환 지점(소문자/숫자 → 대문자)에서 끊으면
# "ChapterDrafterAgent" → "ChapterDrafter"/"Agent", "knowledge/store.json" →
# "knowledge/store."/"json"처럼 의미 단위가 보존된다. `(`/`)`는 경계에서 뺐다 —
# 넣으면 "scores()"처럼 짧은 괄호 쌍이 앞 토큰과 분리돼 그 한 글자만 외로이
# 다음 줄에 남는 경우가 흔했다(예: "query_with_scores(" / ")").
_WORD_BOUNDARY_RE = re.compile(r"(?<=[/_.\-])(?!$)|(?<=[a-z0-9])(?=[A-Z])")


def _char_width(ch: str) -> int:
    cp = ord(ch)
    return 2 if any(lo <= cp <= hi for lo, hi in _WIDE_CHAR_RANGES) else 1


def _visual_width(s: str) -> int:
    return sum(_char_width(c) for c in s)


def _hard_split(text: str, max_width: int) -> list[str]:
    """자연 경계가 없는 텍스트(연속 한글 등)만 문자 단위로 강제 분할한다."""
    lines: list[str] = []
    chunk, chunk_w = "", 0
    for ch in text:
        cw = _char_width(ch)
        if chunk_w + cw > max_width and chunk:
            lines.append(chunk)
            chunk, chunk_w = ch, cw
        else:
            chunk += ch
            chunk_w += cw
    if chunk:
        lines.append(chunk)
    return lines


def _split_long_word(word: str, max_width: int) -> list[str]:
    """공백 없는 긴 단어를 자연 경계(`_WORD_BOUNDARY_RE`) 기준으로 접는다.

    경계가 아예 없는 토큰(긴 한글 연속 등)만 `_hard_split()`으로 문자 단위
    분할한다.
    """
    tokens = [t for t in _WORD_BOUNDARY_RE.split(word) if t]
    lines: list[str] = []
    current, current_w = "", 0
    for tok in tokens:
        tok_w = _visual_width(tok)
        if tok_w > max_width:
            if current:
                lines.append(current)
                current, current_w = "", 0
            sub = _hard_split(tok, max_width)
            lines.extend(sub[:-1])
            current, current_w = sub[-1], _visual_width(sub[-1])
            continue
        if current_w + tok_w > max_width and current:
            lines.append(current)
            current, current_w = tok, tok_w
        else:
            current += tok
            current_w += tok_w
    if current:
        lines.append(current)
    return lines


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
            sub_lines = _split_long_word(word, max_width)
            lines.extend(sub_lines[:-1])
            current, current_w = sub_lines[-1], _visual_width(sub_lines[-1])
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

    `subgraph X["..."]` 줄의 제목 라벨은 이 줄바꿈 대상에서 제외한다. 노드
    라벨은 foreignObject가 실측 높이만큼 스스로 커지지만, Mermaid는 서브그래프
    제목 위에 예약하는 세로 여백을 제목이 원래 한 줄이라는 전제로 고정 계산한다
    — 제목을 여기서 두 줄로 접으면 그 여백 계산이 실제 렌더 높이를 못 따라가,
    둘째 줄이 서브그래프의 첫 자식 노드 박스와 겹쳐 보인다(실측: 2줄 제목의
    foreignObject가 38px인데 첫 자식 노드 상단이 25px 지점에서 시작). 제목이
    길어 한 줄로 넘치면 클러스터 박스가 가로로 넓어질 뿐이고, 그 가로 오버플로는
    HTML(`overflow-x: auto`)과 PDF(폭 기준 축소 스케일) 양쪽에서 이미 처리된다.
    """

    def _sub(m: re.Match) -> str:
        label = _BR_TAG_RE.sub(lambda _m: "\\n", m.group(1))
        return '"' + _wrap_label(label) + '"'

    lines = code.split("\n")
    for i, line in enumerate(lines):
        if _SUBGRAPH_LINE_RE.match(line):
            continue
        lines[i] = _QUOTED_LABEL_RE.sub(_sub, line)
    return "\n".join(lines)
