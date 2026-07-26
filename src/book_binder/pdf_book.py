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
import math
import re
import shutil
import tempfile
from html import escape as _html_escape
from pathlib import Path

from book_binder.manifest import BookConfig, ChapterFile
from book_binder.render import md_to_html, tip_start_pattern

_TEMPLATES_DIR = Path(__file__).parent / "templates"

_PDF_CONTENT_W = 624
_AVAIL_W = _PDF_CONTENT_W - 32
_CHUNK_H = 300


def _rewrite_img_paths(html_str: str, base_dir: Path) -> str:
    """img src의 상대 경로를 file:// 절대 경로로 치환한다 (Playwright 로컬 렌더링용)."""

    def _to_abs(m: re.Match) -> str:
        src = m.group(1)
        if src.startswith(("http://", "https://", "data:", "file://")):
            return m.group(0)
        abs_path = (base_dir / src).resolve()
        return f'src="file://{abs_path}"'

    return re.sub(r'src="([^"]+)"', _to_abs, html_str)


def _build_pdf_page_html(body_html: str, title: str) -> str:
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


async def convert_one(chapter: ChapterFile, browser, tip_pattern, *, out_path: Path) -> Path:
    """챕터 하나를 PDF로 변환한다. 긴 mermaid 다이어그램은 청크 스크린샷으로 대체 삽입한다."""
    out_path.parent.mkdir(parents=True, exist_ok=True)

    raw = chapter.path.read_text(encoding="utf-8")
    body = md_to_html(raw, tip_pattern)
    html = _rewrite_img_paths(_build_pdf_page_html(body, chapter.path.stem), chapter.path.parent)

    temp_dir = Path(tempfile.mkdtemp(prefix="book_binder_pdf_"))
    try:
        ctx1 = await browser.new_context(device_scale_factor=1)
        render_page = await ctx1.new_page()
        await render_page.set_content(html, wait_until="networkidle")
        try:
            await render_page.wait_for_function("() => window.__mermaidDone === true", timeout=20000)
        except Exception:
            pass
        full_h = await render_page.evaluate("() => Math.max(document.body.scrollHeight, 6000)")
        await render_page.set_viewport_size({"width": _PDF_CONTENT_W, "height": full_h})

        mermaid_diagrams: list[list[tuple[str, int, int]]] = []
        n_containers = await render_page.locator(".mermaid").count()

        for idx in range(n_containers):
            try:
                info = await render_page.evaluate(f"""() => {{
                    const container = document.querySelectorAll('.mermaid')[{idx}];
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
                    return {{x: b.x, y: b.y, w: Math.round(b.width), h: Math.round(b.height)}};
                }}""")
                if not info:
                    mermaid_diagrams.append([])
                    continue

                sx, sy, tw, th = info["x"], info["y"], info["w"], info["h"]
                n_chunks = max(1, math.ceil(th / _CHUNK_H))
                chunks: list[tuple[str, int, int]] = []

                for ci in range(n_chunks):
                    ry = round(sy + ci * _CHUNK_H)
                    ch = min(_CHUNK_H, round(sy + th) - ry)
                    if ch <= 0:
                        break
                    png = await render_page.screenshot(
                        type="png",
                        clip={"x": round(sx), "y": ry, "width": tw, "height": ch},
                    )
                    chunk_path = temp_dir / f"mermaid_{idx:04d}_{ci:02d}.png"
                    chunk_path.write_bytes(png)
                    chunks.append((f"file://{chunk_path}", tw, ch))

                mermaid_diagrams.append(chunks)
            except Exception:
                mermaid_diagrams.append([])
                continue
        await render_page.close()
        await ctx1.close()

        p2_html = html
        if any(mermaid_diagrams):
            diag_iter = iter(mermaid_diagrams)

            def _replace_mermaid(m: re.Match) -> str:
                try:
                    chunks = next(diag_iter)
                except StopIteration:
                    return m.group(0)
                if not chunks:
                    return m.group(0)
                n = len(chunks)
                parts = []
                for ci2, (fu, w, h) in enumerate(chunks):
                    mt = "14px" if ci2 == 0 else "0"
                    mb = "14px" if ci2 == n - 1 else "0"
                    parts.append(
                        f'<div class="mermaid-chunk" style="margin:{mt} 0 {mb};'
                        f'display:table;width:100%;break-inside:avoid;page-break-inside:avoid;">'
                        f'<img src="{fu}" width="{w}" height="{h}" '
                        f'style="display:block;margin:0 auto;width:{w}px;height:{h}px;max-width:none;border:none;">'
                        f"</div>"
                    )
                return "".join(parts)

            p2_html = re.sub(
                r'<div\s+class="mermaid"[^>]*>.*?</div>',
                _replace_mermaid,
                p2_html,
                flags=re.DOTALL,
            )

        html_file = temp_dir / "chapter.html"
        html_file.write_text(p2_html, encoding="utf-8")

        ctx2 = await browser.new_context(device_scale_factor=1)
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


async def _run_all(chapters: list[ChapterFile], root: Path, pdf_dir: Path, tip_pattern) -> tuple[int, int]:
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
                await convert_one(chapter, browser, tip_pattern, out_path=out_path)
                ok += 1
            except Exception as exc:
                print(f"  ❌ {rel}: {exc}")
                fail += 1
        await browser.close()
    return ok, fail


async def _run_merged(chapters: list[ChapterFile], out_path: Path, tip_pattern) -> bool:
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
                    await convert_one(chapter, browser, tip_pattern, out_path=part_out)
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
    from book_binder.manifest import resolve

    if config is None:
        config = BookConfig.load(root)

    chapters = resolve(root, config)
    if not chapters:
        raise ValueError(f"변환할 마크다운 파일을 찾지 못했습니다: {root}")

    tip_pattern = tip_start_pattern(config.tip_markers if config else [])
    pdf_dir = out_dir or (root / "pdf")

    if merge_name is not None:
        out_path = pdf_dir / f"{merge_name}.pdf"
        print(f"\U0001f4c4 병합 대상: {len(chapters)}개 파일 → {out_path}")
        ok = asyncio.run(_run_merged(chapters, out_path, tip_pattern))
        if not ok:
            raise RuntimeError("PDF 병합 실패")
        return out_path

    print(f"\U0001f4c4 변환 대상: {len(chapters)}개 파일 → {pdf_dir}")
    ok_n, fail_n = asyncio.run(_run_all(chapters, root, pdf_dir, tip_pattern))
    print(f"완료: {ok_n}개 성공 / {fail_n}개 실패")
    if fail_n:
        raise RuntimeError(f"{fail_n}개 챕터 PDF 변환 실패")
    return [pdf_dir / c.path.relative_to(root).with_suffix(".pdf") for c in chapters]
