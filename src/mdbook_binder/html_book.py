"""마크다운 코퍼스 → 검색 가능한 단일 HTML 도서 빌더.

manifest.resolve()로 얻은 챕터 순서에 render.md_to_html()을 적용하고, 이미지를
base64 data URI로 인라인 임베드해 이미지 폴더 없이도 완전히 독립적으로 열리는
단일 HTML 파일을 만든다.

이 모듈이 출력하는 `<section class="chapter-section" id="{slug}">` 구조는
editor/ 가 의존하는 유일한 불변 계약이다 — 다른 무엇을 바꾸더라도 이 마크업
계약은 유지해야 편집기가 섹션을 인식한다.
"""

from __future__ import annotations

import re
import unicodedata
from html import escape as _html_escape
from pathlib import Path

from mdbook_binder.imgembed import image_to_data_uri
from mdbook_binder.manifest import LOCALE_STRINGS, BookConfig, resolve
from mdbook_binder.mermaid_prerender import (
    mermaid_font_face_css,
    mermaid_label_css,
    prerender_mermaid,
)
from mdbook_binder.render import demote_headings, extract_h1_text, md_to_html, tip_start_pattern
from mdbook_binder.theme import theme_css

_TEMPLATES_DIR = Path(__file__).parent / "templates"


def _slugify(text: str) -> str:
    text = unicodedata.normalize("NFKD", text)
    ascii_only = text.encode("ascii", "ignore").decode("ascii")
    base = ascii_only if ascii_only.strip() else text
    base = re.sub(r"[^\w\s-]", "", base, flags=re.UNICODE).strip().lower()
    slug = re.sub(r"[\s_]+", "-", base)
    return slug or "section"


def _section_id(fpath: Path, html_body: str, config: BookConfig | None) -> str:
    if config and (override := config.section_id_overrides.get(unicodedata.normalize("NFC", fpath.stem))):
        return override
    title = extract_h1_text(html_body)
    return _slugify(title or fpath.stem)


def _dedupe_slug(slug: str, seen: dict[str, int]) -> str:
    """서로 다른 챕터가 같은 제목(따라서 같은 slug)을 쓸 때 id 충돌을 막는다.

    예: 서로 다른 Part에 "개요"라는 제목의 챕터가 둘 있으면 둘 다 slug가
    "개요"가 되어 <section id="개요">가 중복 — 앵커 이동/TOC가 첫 번째
    섹션으로만 깨져서 이동하게 된다. 편집기(editor/html_editor.py)의
    _deduplicate_section_ids()는 편집 시점에만 이를 고치므로, 빌드 시점부터
    애초에 중복 id를 만들지 않도록 여기서 막는다.
    """
    count = seen.get(slug, 0)
    seen[slug] = count + 1
    return slug if count == 0 else f"{slug}-{count + 1}"


def _embed_images_as_data_uri(
    html_str: str, md_dir: Path, missing: list[tuple[Path, str]]
) -> str:
    """img src를 base64 data URI로 인라인 임베드한다.

    http(s)://, data:, file://, # 로 시작하는 src는 이미 절대/인라인이므로 그대로 둔다.
    참조된 이미지가 실제로 없으면(오타 등) `missing`에 기록만 하고 원본 src를
    유지한다 — 관대한 파싱 원칙: 이미지 하나가 빠졌다고 전체 빌드를 실패시키지
    않는다. 대신 build_html()이 빌드 끝에 missing 전체를 한 번에 요약 출력한다
    — 50개가 넘는 챕터의 진행 로그 사이에 경고가 한 줄씩 섞여 나오면 놓치기
    쉽다는 걸 실사용 중 확인했다.
    """

    def _to_data_uri(m: re.Match) -> str:
        src = m.group(1)
        if src.startswith(("http://", "https://", "data:", "file://", "#")):
            return m.group(0)
        abs_path = (md_dir / src).resolve()
        if not abs_path.is_file():
            missing.append((abs_path, src))
            return m.group(0)
        return f'src="{image_to_data_uri(abs_path)}"'

    return re.sub(r'src="([^"]+)"', _to_data_uri, html_str)


def build_html(
    root: Path,
    config: BookConfig | None = None,
    *,
    out_path: Path | None = None,
    title_override: str | None = None,
    language_override: str | None = None,
    color_override: str | None = None,
) -> Path:
    if config is None:
        config = BookConfig.load(root)

    chapters = resolve(root, config)
    if not chapters:
        raise ValueError(f"변환할 마크다운 파일을 찾지 못했습니다: {root}")

    tip_pattern = tip_start_pattern(config.tip_markers if config else [])
    language = language_override or (config.language if config else "ko")
    locale = LOCALE_STRINGS.get(language, LOCALE_STRINGS["ko"])

    sections: list[str] = []
    toc_entries: list[str] = []
    last_part: str | None = None
    seen_slugs: dict[str, int] = {}
    missing_images: list[tuple[Path, str]] = []

    for chap in chapters:
        print(f"  \U0001f4c4 {chap.path.relative_to(root)}")
        raw = chap.path.read_text(encoding="utf-8")
        html_body = md_to_html(raw, tip_pattern)
        html_body = _embed_images_as_data_uri(html_body, chap.path.parent, missing_images)

        sid = _dedupe_slug(_section_id(chap.path, html_body, config), seen_slugs)
        title_text = extract_h1_text(html_body) or chap.path.stem
        html_body = demote_headings(html_body)

        if chap.part_label and chap.part_label != last_part:
            toc_entries.append(f'<a class="part-heading">{_html_escape(chap.part_label)}</a>')
            last_part = chap.part_label

        toc_entries.append(f'<a class="chapter toc-link" href="#{sid}">{_html_escape(title_text)}</a>')
        sections.append(
            f'<section class="chapter-section" id="{sid}" data-section-title="{_html_escape(title_text)}">'
            f"\n{html_body}\n</section>"
        )

    title = title_override or (config.title if config else None) or root.name

    color = color_override or (config.color if config else None)
    css = (_TEMPLATES_DIR / "html_book.css").read_text(encoding="utf-8")
    if color:
        css += f"\n\n{theme_css(color)}"
    if config and (custom_css := config.load_custom_css(root)):
        css += f"\n\n/* ── custom_css (book.yaml) ── */\n{custom_css}"
    js = (_TEMPLATES_DIR / "html_book.js").read_text(encoding="utf-8")
    js = (
        js.replace("__PLACEHOLDER_HITS_FOUND__", locale["hits_found"])
        .replace("__PLACEHOLDER_NO_MATCH__", locale["no_match"])
        .replace("__PLACEHOLDER_OF__", locale["of"])
    )

    body_html, needs_mermaid_cdn = prerender_mermaid("\n".join(sections))
    # 사전 렌더링된 다이어그램이 있을 때만 폰트를 심는다 — 다이어그램이 없는
    # 책까지 base64 폰트(약 2MB)로 무겁게 만들 이유가 없다.
    has_prerendered_diagrams = 'data-prerendered="true"' in body_html
    mermaid_font_css = (
        f"{mermaid_font_face_css()}\n{mermaid_label_css()}" if has_prerendered_diagrams else ""
    )

    html = _render_shell(
        title=title,
        language=language,
        css=css,
        js=js,
        toc_html="\n".join(toc_entries),
        body_html=body_html,
        search_placeholder=locale["search_placeholder"],
        prev_title=locale["prev_title"],
        next_title=locale["next_title"],
        needs_mermaid_cdn=needs_mermaid_cdn,
        mermaid_font_css=mermaid_font_css,
    )

    out = out_path or (root / f"{_slugify(title)}.html")
    out.write_text(html, encoding="utf-8")
    size_kb = out.stat().st_size // 1024
    print(f"\n✅ Done: {out}  ({size_kb} KB, {len(chapters)}개 파일)")

    if missing_images:
        print(f"\n⚠️  누락된 이미지 {len(missing_images)}건 (원본 src 그대로 유지됨):")
        for abs_path, src in missing_images:
            try:
                rel = abs_path.relative_to(root)
            except ValueError:
                rel = abs_path
            print(f"   - {rel}  (참조: \"{src}\")")

    return out


def _render_shell(
    *,
    title: str,
    language: str,
    css: str,
    js: str,
    toc_html: str,
    body_html: str,
    search_placeholder: str,
    prev_title: str,
    next_title: str,
    needs_mermaid_cdn: bool,
    mermaid_font_css: str = "",
) -> str:
    # 다이어그램이 전부(또는 애초에 하나도 없어) 사전 렌더링됐다면 CDN mermaid.js
    # 자체가 필요 없다 — 열람 시 불필요한 외부 요청을 만들지 않도록 태그를 생략한다.
    mermaid_script_tag = (
        '<script src="https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.min.js"></script>\n'
        if needs_mermaid_cdn
        else ""
    )
    return f"""<!DOCTYPE html>
<html lang="{language}">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{_html_escape(title)}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@300;400;500;700&family=Noto+Serif+KR:wght@400;700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
{mermaid_script_tag}<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0/styles/atom-one-dark.min.css">
<script src="https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0/highlight.min.js"></script>
<style>
{mermaid_font_css}
{css}
</style>
</head>
<body>
<nav id="sidebar">
  <div id="sidebar-header">{_html_escape(title)}</div>
  <div id="search-wrap">
    <input id="search-box" type="search" placeholder="{_html_escape(search_placeholder)}" autocomplete="off" spellcheck="false">
    <div id="search-meta">
      <span id="search-count"></span>
      <div id="search-nav">
        <button id="search-prev" disabled title="{_html_escape(prev_title)}">▲</button>
        <button id="search-next" disabled title="{_html_escape(next_title)}">▼</button>
      </div>
    </div>
  </div>
  <div id="toc">
{toc_html}
  </div>
</nav>
<main id="main">
{body_html}
</main>
<script>
{js}
</script>
</body>
</html>
"""
