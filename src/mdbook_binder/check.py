"""빌드 전 사전 점검 — `mdbook-binder check`.

Media/Book을 실제로 변환하며 두 가지를 빌드가 다 끝난 뒤에야(HTML을 열어 섹션
수를 세어보고 나서야) 발견했다: (1) IMAGES.md 같은 집필 가이드 문서가 챕터로
오분류된 것, (2) 이미지 참조 누락. 이 점검을 파일 하나 만들지 않고 미리
할 수 있게 한다 — HTML을 렌더링하지 않고 원본 마크다운만 훑으므로 빠르다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from mdbook_binder.manifest import BookConfig, ChapterFile, resolve_verbose

_H1_RE = re.compile(r"^#\s+(.+)$", re.MULTILINE)
_IMG_SRC_RE = re.compile(r"!\[[^\]]*\]\(([^)]+)\)")


@dataclass
class CheckResult:
    tier: str
    chapters: list[ChapterFile]
    duplicate_titles: dict[str, list[Path]] = field(default_factory=dict)
    missing_images: list[tuple[Path, str]] = field(default_factory=list)


def check_corpus(root: Path, config: BookConfig | None = None) -> CheckResult:
    if config is None:
        config = BookConfig.load(root)

    chapters, tier = resolve_verbose(root, config)

    titles: dict[str, list[Path]] = {}
    missing: list[tuple[Path, str]] = []

    for chap in chapters:
        raw = chap.path.read_text(encoding="utf-8")

        m = _H1_RE.search(raw)
        title = m.group(1).strip() if m else chap.path.stem
        titles.setdefault(title, []).append(chap.path)

        for img_match in _IMG_SRC_RE.finditer(raw):
            src = img_match.group(1)
            if src.startswith(("http://", "https://", "data:", "#")):
                continue
            abs_path = (chap.path.parent / src).resolve()
            if not abs_path.is_file():
                missing.append((abs_path, src))

    duplicates = {t: paths for t, paths in titles.items() if len(paths) > 1}

    return CheckResult(tier=tier, chapters=chapters, duplicate_titles=duplicates, missing_images=missing)


def format_report(root: Path, result: CheckResult) -> str:
    lines: list[str] = []
    lines.append(f"순서 해석: {result.tier}")
    lines.append(f"챕터 수: {len(result.chapters)}개")
    lines.append("")
    last_part = None
    for chap in result.chapters:
        if chap.part_label and chap.part_label != last_part:
            lines.append(f"[{chap.part_label}]")
            last_part = chap.part_label
        lines.append(f"  - {chap.path.relative_to(root)}")

    if result.duplicate_titles:
        lines.append("")
        lines.append(f"⚠️  같은 제목을 쓰는 챕터 {len(result.duplicate_titles)}건 "
                      "(빌드 시 id에 -2, -3... 자동 부여됨):")
        for title, paths in result.duplicate_titles.items():
            rels = ", ".join(str(p.relative_to(root)) for p in paths)
            lines.append(f"   - \"{title}\": {rels}")

    if result.missing_images:
        lines.append("")
        lines.append(f"⚠️  누락된 이미지 {len(result.missing_images)}건:")
        for abs_path, src in result.missing_images:
            try:
                rel = abs_path.relative_to(root)
            except ValueError:
                rel = abs_path
            lines.append(f"   - {rel}  (참조: \"{src}\")")

    if not result.duplicate_titles and not result.missing_images:
        lines.append("")
        lines.append("✅ 문제 없음")

    return "\n".join(lines)
