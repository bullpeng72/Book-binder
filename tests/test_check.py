"""check.check_corpus()의 빌드 전 사전 점검 검증."""

from pathlib import Path

from book_binder.check import check_corpus
from book_binder.manifest import TIER_NATURAL_SORT, TIER_PART_CONVENTION


def _write(root: Path, rel: str, content: str) -> Path:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return p


def test_reports_used_tier(tmp_path: Path):
    _write(tmp_path, "a.md", "# A\n\n본문\n")
    result = check_corpus(tmp_path)
    assert result.tier == TIER_NATURAL_SORT


def test_detects_duplicate_titles_without_building(tmp_path: Path):
    _write(tmp_path, "Part_I_A/Chapter_01_x.md", "# 개요\n\nPart I\n")
    _write(tmp_path, "Part_II_B/Chapter_01_y.md", "# 개요\n\nPart II\n")

    result = check_corpus(tmp_path)

    assert result.tier == TIER_PART_CONVENTION
    assert "개요" in result.duplicate_titles
    assert len(result.duplicate_titles["개요"]) == 2


def test_detects_missing_image_reference(tmp_path: Path):
    _write(tmp_path, "chapter.md", "# 챕터\n\n![그림](./images/missing.png)\n")

    result = check_corpus(tmp_path)

    assert len(result.missing_images) == 1
    assert result.missing_images[0][1] == "./images/missing.png"


def test_no_false_positive_for_remote_or_data_uri_images(tmp_path: Path):
    _write(
        tmp_path,
        "chapter.md",
        "# 챕터\n\n![원격](https://example.com/x.png)\n\n![인라인](data:image/png;base64,AAA)\n",
    )

    result = check_corpus(tmp_path)

    assert result.missing_images == []
