"""editor/server.py의 `/api/images/serve` 경로 화이트리스트 회귀 테스트.

과거엔 `str(path).startswith(str(allowed_root))` 문자열 접두사 비교를 썼는데,
이는 "/tmp/book_project"와 "/tmp/book_project_evil" 같은 형제 디렉토리를
구분하지 못해 화이트리스트를 우회당할 수 있었다(경로 구성요소 단위가 아니라
문자열 단위 비교라서). `Path.is_relative_to()`로 바뀐 뒤에도 정상 경로는 계속
서빙되고, 형제 디렉토리 우회는 차단되는지 고정한다.
"""

from pathlib import Path

from mdbook_binder.editor.server import create_app
from mdbook_binder.html_book import build_html

_PNG_BYTES = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108020000009077"
    "53de0000000c4944415408d763f8cfc0c0c00000030101006bec38ba0000000049454e44ae426082"
)


def _build_book(root: Path) -> Path:
    (root / "chapter.md").write_text("# 챕터\n\n본문.\n", encoding="utf-8")
    return build_html(root, config=None, out_path=root / "book.html")


def test_serve_image_allows_file_inside_allowed_root(tmp_path: Path):
    html_path = _build_book(tmp_path)
    img_path = tmp_path / "inside.png"
    img_path.write_bytes(_PNG_BYTES)

    client = create_app(str(html_path)).test_client()
    resp = client.get("/api/images/serve", query_string={"path": str(img_path)})

    assert resp.status_code == 200


def test_serve_image_rejects_sibling_directory_with_shared_prefix(tmp_path: Path):
    """형제 디렉토리(`book_evil`)가 허용 루트(`book`)와 문자열 접두사를 공유해도
    거부돼야 한다 — startswith() 비교였을 때 우회 가능했던 케이스."""
    root = tmp_path / "book"
    root.mkdir()
    html_path = _build_book(root)

    evil_root = tmp_path / "book_evil"
    evil_root.mkdir()
    secret = evil_root / "secret.png"
    secret.write_bytes(_PNG_BYTES)

    client = create_app(str(html_path)).test_client()
    resp = client.get("/api/images/serve", query_string={"path": str(secret)})

    assert resp.status_code == 403


def test_serve_image_rejects_path_outside_allowed_roots(tmp_path: Path):
    html_path = _build_book(tmp_path)
    outside = tmp_path.parent / "outside.png"
    outside.write_bytes(_PNG_BYTES)
    try:
        client = create_app(str(html_path)).test_client()
        resp = client.get("/api/images/serve", query_string={"path": str(outside)})

        assert resp.status_code == 403
    finally:
        outside.unlink()
