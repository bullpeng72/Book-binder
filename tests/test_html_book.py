"""html_book.build_html()의 회귀 테스트 — 특히 섹션 id 충돌 회피."""

from pathlib import Path

from book_binder.html_book import build_html


def _write(root: Path, rel: str, content: str) -> Path:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return p


def test_duplicate_chapter_titles_get_distinct_section_ids(tmp_path: Path):
    """서로 다른 Part의 챕터 제목이 우연히 같아도(예: "개요") id가 충돌하면 안 된다.

    회귀 대상: 예전엔 두 섹션 모두 <section id="개요">가 되어 TOC 링크가 항상
    첫 번째 섹션으로만 이동했다.
    """
    _write(tmp_path, "Part_I_A/Chapter_01_x.md", "# 개요\n\nPart I의 개요.\n")
    _write(tmp_path, "Part_II_B/Chapter_01_y.md", "# 개요\n\nPart II의 개요.\n")

    out = build_html(tmp_path, config=None, out_path=tmp_path / "out.html")
    html = out.read_text(encoding="utf-8")

    ids = [seg.split('"')[0] for seg in html.split('<section class="chapter-section" id="')[1:]]
    assert len(ids) == len(set(ids)), f"중복 id 발견: {ids}"


def test_build_html_creates_one_section_per_chapter(tmp_path: Path):
    _write(tmp_path, "a.md", "# A\n\n본문 A.\n")
    _write(tmp_path, "b.md", "# B\n\n본문 B.\n")

    out = build_html(tmp_path, config=None, out_path=tmp_path / "out.html")
    html = out.read_text(encoding="utf-8")

    assert html.count('class="chapter-section"') == 2


def test_image_embedded_as_base64_data_uri(tmp_path: Path):
    img_bytes = bytes.fromhex(
        "89504e470d0a1a0a0000000d49484452000000010000000108020000009077"
        "53de0000000c4944415408d763f8cfc0c0c00000030101006bec38ba0000000049454e44ae426082"
    )
    _write(tmp_path, "images/pic.png", "")
    (tmp_path / "images" / "pic.png").write_bytes(img_bytes)
    _write(tmp_path, "chapter.md", "# 챕터\n\n![그림](./images/pic.png)\n")

    out = build_html(tmp_path, config=None, out_path=tmp_path / "out.html")
    html = out.read_text(encoding="utf-8")

    assert 'src="data:image/png;base64,' in html
    assert "images/pic.png" not in html.replace('src="data:image/png;base64,', "")
