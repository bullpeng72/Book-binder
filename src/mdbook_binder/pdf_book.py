"""마크다운 코퍼스 → 챕터별 PDF(개별 또는 --merge 단권) 빌더.

Playwright/Chromium으로 각 챕터를 독립 렌더링한다. Mermaid 다이어그램은 청크
단위로 스크린샷 캡처해 삽입한다 — Chromium PDF 엔진이 매우 긴 SVG를 페이지
경계에서 잘라버리는 문제를 피하기 위함이다(`build_pdf_chapters.py`에서 검증된
방식을 그대로 이식). 병합(`--merge`)도 각 챕터를 동일한 코드 경로로 개별
렌더링한 뒤 pypdf로 PDF 객체 레벨에서 합친다 — 개별 생성과 병합 생성의 폰트
크기·다이어그램 해상도가 항상 동일하게 유지된다.
"""

from __future__ import annotations

import asyncio
import re
import shutil
import tempfile
from html import escape as _html_escape
from pathlib import Path

from mdbook_binder.manifest import BookConfig, ChapterFile
from mdbook_binder.render import md_to_html, tip_start_pattern

_TEMPLATES_DIR = Path(__file__).parent / "templates"

_PDF_CONTENT_W = 624
_AVAIL_W = _PDF_CONTENT_W - 32
_CHUNK_H = 300

# Mermaid 스크린샷 캡처 및 최종 PDF 래스터화 해상도 배율.
# 1이면 CSS px = 물리 px(96dpi 상당)로 캡처되어 인쇄/확대 시 다이어그램과
# 이미지가 흐릿해진다. getBoundingClientRect() 등 레이아웃 계산은 항상 CSS px
# 기준이라 clip 좌표·페이지 나눔 로직에는 영향 없이 캡처 해상도만 올라간다.
_DEVICE_SCALE = 3


def _rewrite_img_paths(html_str: str, base_dir: Path) -> str:
    """img src의 상대 경로를 file:// 절대 경로로 치환한다 (Playwright 로컬 렌더링용)."""

    def _to_abs(m: re.Match) -> str:
        src = m.group(1)
        if src.startswith(("http://", "https://", "data:", "file://")):
            return m.group(0)
        abs_path = (base_dir / src).resolve()
        return f'src="file://{abs_path}"'

    return re.sub(r'src="([^"]+)"', _to_abs, html_str)


def _merge_bands(bands: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """겹치는 (y0, y1) 구간들을 하나로 합친다."""
    if not bands:
        return []
    ordered = sorted(bands)
    merged = [list(ordered[0])]
    for s, e in ordered[1:]:
        if s <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], e)
        else:
            merged.append([s, e])
    return [(s, e) for s, e in merged]


def _is_occupied(y: float, bands: list[tuple[float, float]]) -> bool:
    return any(s < y < e for s, e in bands)


def _nearest_safe_y(target: float, bands: list[tuple[float, float]], lo: float, hi: float) -> float:
    """target 근방에서 도형/텍스트와 겹치지 않는 y좌표를 찾는다. 못 찾으면 target 그대로 반환한다."""
    if lo > hi:
        return target
    target = max(lo, min(hi, target))
    if not _is_occupied(target, bands):
        return target
    offset = 2.0
    while True:
        left, right = target - offset, target + offset
        left_ok, right_ok = left >= lo, right <= hi
        if not left_ok and not right_ok:
            return target
        if left_ok and not _is_occupied(left, bands):
            return left
        if right_ok and not _is_occupied(right, bands):
            return right
        offset += 2.0


def _chunk_boundaries(th: float, bands_raw: list[tuple[float, float]], chunk_h: int) -> list[float]:
    """다이어그램 전체 높이(th)를 chunk_h 근처 간격으로 나누되, 도형/텍스트 중앙을 피해
    자연스러운 여백에서 끊는 경계 목록을 반환한다.

    고정된 chunk_h 간격으로만 자르면 박스나 라벨이 정확히 경계에 걸렸을 때 그대로
    반토막나고, 그 반쪽 청크가 PDF 페이지 경계에 걸리면 도형이 시각적으로 잘려
    보인다. 각 경계를 목표 지점 주변에서 비어 있는(도형이 없는) y좌표로 옮겨
    이를 피한다.
    """
    if th <= chunk_h:
        return [0.0, float(th)]
    bands = _merge_bands(bands_raw)
    min_chunk = chunk_h * 0.4
    max_chunk = chunk_h * 1.6
    boundaries = [0.0]
    y = 0.0
    while y < th:
        target = y + chunk_h
        if target >= th:
            boundaries.append(float(th))
            break
        safe = _nearest_safe_y(target, bands, y + min_chunk, min(y + max_chunk, th))
        boundaries.append(safe)
        y = safe
    return boundaries


def _mermaid_chunk_html(chunks: list[tuple[str, int, int]]) -> str:
    """mermaid 컨테이너를 대체할 청크 스크린샷 <img> 마크업을 만든다."""
    n = len(chunks)
    parts = []
    for ci, (fu, w, h) in enumerate(chunks):
        mt = "14px" if ci == 0 else "0"
        mb = "14px" if ci == n - 1 else "0"
        parts.append(
            f'<div class="mermaid-chunk" style="margin:{mt} 0 {mb};'
            f'display:table;width:100%;break-inside:avoid;page-break-inside:avoid;">'
            f'<img src="{fu}" width="{w}" height="{h}" '
            f'style="display:block;margin:0 auto;width:{w}px;height:{h}px;max-width:none;border:none;">'
            f"</div>"
        )
    return "".join(parts)


def _build_pdf_page_html(body_html: str, title: str, custom_css: str = "") -> str:
    css = (_TEMPLATES_DIR / "html_book.css").read_text(encoding="utf-8")
    pdf_css = (_TEMPLATES_DIR / "pdf_override.css").read_text(encoding="utf-8")
    js = (_TEMPLATES_DIR / "pdf_book.js").read_text(encoding="utf-8")
    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<title>{_html_escape(title)}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@300;400;500;700&family=Noto+Serif+KR:wght@400;700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0/styles/atom-one-dark.min.css">
<script src="https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0/highlight.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.min.js"></script>
<style>
{css}
{pdf_css}
{custom_css}
</style>
</head>
<body>
<main id="main">
{body_html}
</main>
<script>
{js}
</script>
</body>
</html>"""


async def convert_one(
    chapter: ChapterFile, browser, tip_pattern, *, out_path: Path, custom_css: str = ""
) -> Path:
    """챕터 하나를 PDF로 변환한다. 긴 mermaid 다이어그램은 청크 스크린샷으로 대체 삽입한다."""
    out_path.parent.mkdir(parents=True, exist_ok=True)

    raw = chapter.path.read_text(encoding="utf-8")
    body = md_to_html(raw, tip_pattern)
    html = _rewrite_img_paths(
        _build_pdf_page_html(body, chapter.path.stem, custom_css), chapter.path.parent
    )

    temp_dir = Path(tempfile.mkdtemp(prefix="book_binder_pdf_"))
    try:
        # 뷰포트 폭은 처음부터 PDF 목표 폭(_PDF_CONTENT_W)으로 고정한다. 폭을 기본값(1280px)
        # 그대로 두면 pdf_book.js의 mermaid/table 스케일 계산이 잘못된(더 넓은) availW
        # 기준으로 이뤄지고, 이후 뷰포트를 좁히는 순간 텍스트 줄바꿈이 늘어나 문서가
        # 측정한 full_h보다 더 길어진다 — 문서 끝부분 요소가 뷰포트 밖으로 밀려나면
        # screenshot(clip=...)이 좌표를 벗어나 캡처 실패(빈 chunk → 원본 mermaid div
        # 그대로 잔존)로 이어져 빈 페이지가 삽입되고, 가로형 다이어그램은 잘못된
        # availW 기준으로 스케일되어 과대 표시된다.
        ctx1 = await browser.new_context(
            device_scale_factor=_DEVICE_SCALE,
            viewport={"width": _PDF_CONTENT_W, "height": 800},
        )
        render_page = await ctx1.new_page()
        await render_page.set_content(html, wait_until="networkidle")
        try:
            await render_page.wait_for_function("() => window.__mermaidDone === true", timeout=20000)
        except Exception:
            pass
        full_h = await render_page.evaluate("() => Math.max(document.body.scrollHeight, 6000)")
        await render_page.set_viewport_size({"width": _PDF_CONTENT_W, "height": full_h})

        containers = await render_page.query_selector_all(".mermaid")

        for idx, container in enumerate(containers):
            try:
                info = await container.evaluate(f"""(container) => {{
                    const svg = container.querySelector('svg');
                    if (!svg) return null;
                    const r = svg.getBoundingClientRect();
                    if (r.width <= 0 || r.height <= 0) return null;
                    const scW = r.width > {_AVAIL_W} ? {_AVAIL_W} / r.width : 1;
                    const tw = Math.ceil(r.width  * scW);
                    const th = Math.ceil(r.height * scW);
                    svg.setAttribute('width',  tw);
                    svg.setAttribute('height', th);
                    svg.style.cssText = 'display:block;margin:0 auto;';
                    const b = svg.getBoundingClientRect();
                    // 도형/텍스트가 차지하는 y구간을 모아, 청크 경계가 그 한가운데를
                    // 가로지르지 않도록 한다 (박스/라벨이 반토막나는 것을 방지).
                    const bands = [];
                    svg.querySelectorAll('rect, polygon, circle, ellipse, text, path, image').forEach(el => {{
                        const er = el.getBoundingClientRect();
                        if (er.width <= 0 || er.height <= 0) return;
                        const y0 = er.top - b.y;
                        const y1 = er.bottom - b.y;
                        if (y1 <= 0 || y0 >= b.height) return;
                        bands.push([Math.max(0, y0), Math.min(b.height, y1)]);
                    }});
                    return {{x: b.x, y: b.y, w: Math.round(b.width), h: Math.round(b.height), bands}};
                }}""")
                if not info:
                    continue

                sx, sy, tw, th = info["x"], info["y"], info["w"], info["h"]
                bands = [(b[0], b[1]) for b in info.get("bands", [])]
                boundaries = _chunk_boundaries(th, bands, _CHUNK_H)
                chunks: list[tuple[str, int, int]] = []

                for ci in range(len(boundaries) - 1):
                    y0, y1 = boundaries[ci], boundaries[ci + 1]
                    ry = round(sy + y0)
                    ch = round(y1 - y0)
                    if ch <= 0:
                        continue
                    png = await render_page.screenshot(
                        type="png",
                        clip={"x": round(sx), "y": ry, "width": tw, "height": ch},
                    )
                    chunk_path = temp_dir / f"mermaid_{idx:04d}_{ci:02d}.png"
                    chunk_path.write_bytes(png)
                    chunks.append((f"file://{chunk_path}", tw, ch))

                if not chunks:
                    continue

                # container 자체를 청크 이미지로 교체한다 — 문자열 정규식이 아니라
                # DOM 노드 단위 치환이라, mermaid SVG 내부에 중첩된 <div>(foreignObject
                # 라벨)가 몇 개든 컨테이너 경계를 잘못 잡을 일이 없다.
                await container.evaluate("(el, html) => { el.outerHTML = html; }", _mermaid_chunk_html(chunks))
            except Exception:
                continue

        p2_html = await render_page.content()
        await render_page.close()
        await ctx1.close()

        html_file = temp_dir / "chapter.html"
        html_file.write_text(p2_html, encoding="utf-8")

        ctx2 = await browser.new_context(device_scale_factor=_DEVICE_SCALE)
        page = await ctx2.new_page()
        await page.set_viewport_size({"width": _PDF_CONTENT_W, "height": 6000})
        await page.goto(f"file://{html_file}", wait_until="networkidle")
        await page.wait_for_load_state("load")
        try:
            await page.wait_for_function("() => window.__mermaidDone === true", timeout=10000)
        except Exception:
            pass

        real_h = await page.evaluate("document.body.scrollHeight")
        await page.set_viewport_size({"width": _PDF_CONTENT_W, "height": max(real_h, 6000)})

        await page.pdf(
            path=str(out_path),
            format="A4",
            margin={"top": "22mm", "right": "20mm", "bottom": "25mm", "left": "25mm"},
            print_background=True,
        )
        await page.close()
        await ctx2.close()
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)

    size_kb = out_path.stat().st_size // 1024
    print(f"  ✅ {chapter.path.name}  ({size_kb} KB)")
    return out_path


async def _run_all(
    chapters: list[ChapterFile], root: Path, pdf_dir: Path, tip_pattern, custom_css: str = ""
) -> tuple[int, int]:
    from playwright.async_api import async_playwright

    ok = fail = 0
    async with async_playwright() as pw:
        browser = await _launch_chromium(pw)
        if browser is None:
            return 0, len(chapters)
        for chapter in chapters:
            rel = chapter.path.relative_to(root)
            out_path = pdf_dir / rel.with_suffix(".pdf")
            try:
                await convert_one(chapter, browser, tip_pattern, out_path=out_path, custom_css=custom_css)
                ok += 1
            except Exception as exc:
                print(f"  ❌ {rel}: {exc}")
                fail += 1
        await browser.close()
    return ok, fail


async def _run_merged(
    chapters: list[ChapterFile], out_path: Path, tip_pattern, custom_css: str = ""
) -> bool:
    import pypdf
    from playwright.async_api import async_playwright

    out_path.parent.mkdir(parents=True, exist_ok=True)
    temp_dir = Path(tempfile.mkdtemp(prefix="book_binder_merge_"))
    try:
        async with async_playwright() as pw:
            browser = await _launch_chromium(pw)
            if browser is None:
                return False
            part_paths: list[Path] = []
            try:
                for idx, chapter in enumerate(chapters):
                    part_out = temp_dir / f"{idx:03d}.pdf"
                    await convert_one(chapter, browser, tip_pattern, out_path=part_out, custom_css=custom_css)
                    part_paths.append(part_out)
            finally:
                await browser.close()

        writer = pypdf.PdfWriter()
        for part_path in part_paths:
            writer.append(str(part_path))
        with open(out_path, "wb") as f:
            writer.write(f)
        writer.close()
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)

    size_kb = out_path.stat().st_size // 1024
    print(f"  ✅ {out_path.name}  ({len(chapters)}개 파일 병합, {size_kb} KB)")
    return True


async def _launch_chromium(pw):
    try:
        return await pw.chromium.launch()
    except Exception as e:
        if "Executable doesn't exist" in str(e):
            print("\n❌ Playwright 브라우저 엔진이 설치되지 않았습니다.")
            print("   python -m playwright install chromium")
            return None
        raise


def build_pdf(
    root: Path,
    config: BookConfig | None = None,
    *,
    merge_name: str | None = None,
    out_dir: Path | None = None,
) -> Path | list[Path]:
    """ROOT의 마크다운 코퍼스를 PDF로 빌드한다.

    merge_name이 주어지면 단권(out_dir/{merge_name}.pdf), 아니면 챕터별 개별
    PDF(out_dir 아래 디렉토리 구조 그대로)를 만든다. 순서 해석은
    manifest.resolve()의 3단계 우선순위를 html_book.build_html()과 동일하게
    공유한다.
    """
    from mdbook_binder.manifest import resolve

    if config is None:
        config = BookConfig.load(root)

    chapters = resolve(root, config)
    if not chapters:
        raise ValueError(f"변환할 마크다운 파일을 찾지 못했습니다: {root}")

    tip_pattern = tip_start_pattern(config.tip_markers if config else [])
    custom_css = config.load_custom_css(root) if config else ""
    pdf_dir = out_dir or (root / "pdf")

    if merge_name is not None:
        out_path = pdf_dir / f"{merge_name}.pdf"
        print(f"\U0001f4c4 병합 대상: {len(chapters)}개 파일 → {out_path}")
        ok = asyncio.run(_run_merged(chapters, out_path, tip_pattern, custom_css))
        if not ok:
            raise RuntimeError("PDF 병합 실패")
        return out_path

    print(f"\U0001f4c4 변환 대상: {len(chapters)}개 파일 → {pdf_dir}")
    ok_n, fail_n = asyncio.run(_run_all(chapters, root, pdf_dir, tip_pattern, custom_css))
    print(f"완료: {ok_n}개 성공 / {fail_n}개 실패")
    if fail_n:
        raise RuntimeError(f"{fail_n}개 챕터 PDF 변환 실패")
    return [pdf_dir / c.path.relative_to(root).with_suffix(".pdf") for c in chapters]
