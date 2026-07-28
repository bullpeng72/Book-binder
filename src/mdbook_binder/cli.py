"""mdbook-binder CLI.

    mdbook-binder check      <root>                                     빌드 전 사전 점검
    mdbook-binder build html <root> [--out FILE] [--title TITLE] [--language ko|en] [--color NAME]
    mdbook-binder build pdf  <root> [--merge [이름]] [--out-dir ...] [--color NAME]
    mdbook-binder edit       <html>  [--port 5757] [--out ...] [--no-browser]
"""

from __future__ import annotations

from pathlib import Path

import click

from mdbook_binder import __version__
from mdbook_binder.manifest import BookConfig
from mdbook_binder.theme import THEMES

_COLOR_CHOICE = click.Choice(sorted(THEMES), case_sensitive=False)
_COLOR_HELP = "사이드바/제목 강조색 테마 (기본: book.yaml의 color 또는 purple)"


@click.group()
@click.version_option(__version__, prog_name="mdbook-binder")
def main() -> None:
    """mdbook-binder — 마크다운 코퍼스를 HTML/PDF 도서로 변환한다."""


@main.command("check")
@click.argument("root", type=click.Path(exists=True, file_okay=False, path_type=Path))
def check_cmd(root: Path) -> None:
    """ROOT의 마크다운 코퍼스를 실제로 빌드하지 않고 미리 점검한다.

    순서 해석이 어느 단계(1~3순위)로 결정됐는지, 중복 제목·누락 이미지가
    있는지를 원본 마크다운만 훑어 빠르게 보여준다 — 챕터로 잘못 분류된
    문서(예: 집필 가이드 .md)를 빌드 후에야 발견하는 일을 줄이기 위함이다.
    """
    from mdbook_binder.check import check_corpus, format_report

    result = check_corpus(root)
    print(format_report(root, result))


@main.group("build")
def build() -> None:
    """HTML 또는 PDF 도서를 빌드한다."""


@build.command("html")
@click.argument("root", type=click.Path(exists=True, file_okay=False, path_type=Path))
@click.option("--out", "out_path", type=click.Path(path_type=Path), default=None, help="출력 HTML 경로")
@click.option("--title", "title_override", default=None, help="book.yaml의 title을 오버라이드")
@click.option("--language", "language_override", default=None, help="book.yaml의 language를 오버라이드 (ko/en)")
@click.option("--color", "color_override", type=_COLOR_CHOICE, default=None, help=_COLOR_HELP)
def build_html_cmd(
    root: Path,
    out_path: Path | None,
    title_override: str | None,
    language_override: str | None,
    color_override: str | None,
) -> None:
    """ROOT 아래 마크다운 코퍼스를 검색 가능한 단일 HTML 도서로 빌드한다."""
    from mdbook_binder.html_book import build_html

    print(f"\U0001f4da Building HTML book from {root} ...")
    config = BookConfig.load(root)
    build_html(
        root,
        config,
        out_path=out_path,
        title_override=title_override,
        language_override=language_override,
        color_override=color_override,
    )


@build.command("pdf")
@click.argument("root", type=click.Path(exists=True, file_okay=False, path_type=Path))
@click.option("--merge", "merge_out", is_flag=False, flag_value="full_book", default=None,
              help="지정한 파일들을 하나의 PDF로 병합 (값 생략 시 full_book)")
@click.option("--out-dir", "out_dir", type=click.Path(path_type=Path), default=None,
              help="PDF 출력 디렉토리 (기본: ROOT/pdf)")
@click.option("--color", "color_override", type=_COLOR_CHOICE, default=None, help=_COLOR_HELP)
def build_pdf_cmd(
    root: Path, merge_out: str | None, out_dir: Path | None, color_override: str | None
) -> None:
    """ROOT 아래 마크다운을 챕터별 PDF(또는 --merge 시 단권)로 빌드한다."""
    from mdbook_binder.pdf_book import build_pdf

    print(f"\U0001f4da Building PDF from {root} ...")
    try:
        build_pdf(root, merge_name=merge_out, out_dir=out_dir, color_override=color_override)
    except RuntimeError as exc:
        raise click.ClickException(str(exc)) from exc


@main.command("edit")
@click.argument("html_path", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option("--port", "-p", type=int, default=5757, help="에디터 서버 포트")
@click.option("--out", "out_path", type=click.Path(path_type=Path), default=None, help="저장 경로 (기본: <stem>_edited.html)")
@click.option("--no-browser", is_flag=True, default=False, help="브라우저 자동 오픈 비활성화")
def edit_cmd(html_path: Path, port: int, out_path: Path | None, no_browser: bool) -> None:
    """HTML_PATH를 브라우저 편집 UI로 연다."""
    from mdbook_binder.editor.server import run_editor

    run_editor(
        str(html_path),
        output_path=str(out_path) if out_path else None,
        port=port,
        open_browser=not no_browser,
    )


if __name__ == "__main__":
    main()
