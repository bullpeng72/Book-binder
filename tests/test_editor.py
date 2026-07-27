"""editor/ 이미지 추가·교체 후 저장 시 base64 임베드 회귀 테스트.

과거엔 img src에 파일 경로를 그대로 써서, 편집기로 저장한 HTML이 최초
빌드본과 달리 이미지 폴더에 의존하는 문제가 있었다.
"""

from collections import defaultdict
from pathlib import Path

from mdbook_binder.editor.html_editor import BookHTMLEditor
from mdbook_binder.editor.image_editor import ImageEditor
from mdbook_binder.html_book import build_html

_PNG_BYTES = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108020000009077"
    "53de0000000c4944415408d763f8cfc0c0c00000030101006bec38ba0000000049454e44ae426082"
)


def _write(root: Path, rel: str, content: str) -> Path:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return p


def _apply_and_save(html_editor: BookHTMLEditor, image_editor: ImageEditor, out_path: Path) -> str:
    """server.py의 /api/save와 동일한 순서로 변경을 적용·저장한다."""
    updated_soup = html_editor.apply_all_changes()

    src_map: dict = defaultdict(list)
    for tag in updated_soup.find_all("img"):
        src_map[tag.get("src", "")].append(tag)
    for img_info in image_editor.images:
        live = src_map.get(img_info["src"], [])
        if live:
            img_info["tag"] = live.pop(0)

    image_editor.soup = updated_soup
    return image_editor.save_changes(str(out_path))


def test_added_image_embedded_as_base64(tmp_path: Path):
    (tmp_path / "new.png").write_bytes(_PNG_BYTES)
    _write(tmp_path, "chapter.md", "# 챕터\n\n본문.\n")
    html_path = build_html(tmp_path, config=None, out_path=tmp_path / "book.html")

    html_editor = BookHTMLEditor(str(html_path))
    image_editor = ImageEditor(str(html_path))
    sec_id = html_editor.get_book_meta()["sections"][0]["id"]

    assert html_editor.stage_add_image(sec_id, str(tmp_path / "new.png"), "캡션")

    out = tmp_path / "book_edited.html"
    _apply_and_save(html_editor, image_editor, out)
    html = Path(out).read_text(encoding="utf-8")

    assert 'src="data:image/png;base64,' in html
    assert str(tmp_path) not in html


def test_replaced_image_embedded_as_base64(tmp_path: Path):
    (tmp_path / "images").mkdir()
    (tmp_path / "images" / "orig.png").write_bytes(_PNG_BYTES)
    (tmp_path / "new.png").write_bytes(_PNG_BYTES)
    _write(tmp_path, "chapter.md", "# 챕터\n\n![그림](./images/orig.png)\n")
    html_path = build_html(tmp_path, config=None, out_path=tmp_path / "book.html")

    html_editor = BookHTMLEditor(str(html_path))
    image_editor = ImageEditor(str(html_path))

    assert image_editor.replace_image(1, str(tmp_path / "new.png"))

    out = tmp_path / "book_edited.html"
    _apply_and_save(html_editor, image_editor, out)
    html = Path(out).read_text(encoding="utf-8")

    assert html.count('src="data:image/png;base64,') == 1
    assert str(tmp_path) not in html
