"""manifest.resolve()의 3단계 우선순위 검증."""

from pathlib import Path

from mdbook_binder.manifest import BookConfig, OrderConfig, resolve


def _write(root: Path, rel: str, content: str = "# Title\n\nbody\n") -> Path:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return p


def test_natural_sort_fallback_includes_all_loose_files(tmp_path: Path):
    """1/1.5/2순위가 전부 실패하면(명명 규칙 없음) 트리 전체를 자연정렬로 포함한다."""
    _write(tmp_path, "b.md")
    _write(tmp_path, "a.md")
    _write(tmp_path, "sub/c.md")

    chapters = resolve(tmp_path, config=None)

    assert [c.path.name for c in chapters] == ["a.md", "b.md", "c.md"]


def test_explicit_config_order_wins_over_alphabetical(tmp_path: Path):
    """book.yaml의 order.files가 자연정렬보다 우선한다."""
    _write(tmp_path, "a.md")
    _write(tmp_path, "b.md")
    config = BookConfig(order=OrderConfig(files=["b.md", "a.md"]))

    chapters = resolve(tmp_path, config)

    assert [c.path.name for c in chapters] == ["b.md", "a.md"]


def test_part_chapter_convention_orders_by_roman_numeral(tmp_path: Path):
    """Part_로마숫자 규칙이 있으면 II보다 III이 뒤에, 알파벳순이 아니라 로마숫자 순으로 온다."""
    _write(tmp_path, "Part_III_third/Chapter_01_x.md")
    _write(tmp_path, "Part_I_first/Chapter_01_x.md")
    _write(tmp_path, "Part_II_second/Chapter_01_x.md")

    chapters = resolve(tmp_path, config=None)

    parts = [c.path.parent.name for c in chapters]
    assert parts == ["Part_I_first", "Part_II_second", "Part_III_third"]


def test_back_matter_and_appendix_ordered_after_parts(tmp_path: Path):
    """9x_ 접두사 후주와 Appendix/는 Part 챕터들 뒤에 온다(정면 회귀 대상 버그)."""
    _write(tmp_path, "00_intro.md")
    _write(tmp_path, "99_afterword.md")
    _write(tmp_path, "Part_I_only/Chapter_01_x.md")
    _write(tmp_path, "Appendix/A_glossary.md")

    chapters = resolve(tmp_path, config=None)

    names = [c.path.name for c in chapters]
    assert names == ["00_intro.md", "Chapter_01_x.md", "99_afterword.md", "A_glossary.md"]


def test_toc_manifest_auto_detected_without_config(tmp_path: Path):
    """book.yaml 없이도 ```toc 펜스가 있는 파일을 자동으로 매니페스트로 채택한다."""
    _write(tmp_path, "Part_I_intro/Chapter_01_hello.md")
    _write(
        tmp_path,
        "00_toc.md",
        "# 목차\n\n```toc\n1|서론|1|hello|narrative\n```\n",
    )

    chapters = resolve(tmp_path, config=None)

    assert len(chapters) == 1
    assert chapters[0].path.name == "Chapter_01_hello.md"
    assert chapters[0].part_label == "Part 1. 서론"
