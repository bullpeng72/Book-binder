"""빌드 전 사전 점검 — `mdbook-binder check`.

Media/Book을 실제로 변환하며 두 가지를 빌드가 다 끝난 뒤에야(HTML을 열어 섹션
수를 세어보고 나서야) 발견했다: (1) IMAGES.md 같은 집필 가이드 문서가 챕터로
오분류된 것, (2) 이미지 참조 누락. 이 점검을 파일 하나 만들지 않고 미리
할 수 있게 한다 — HTML을 렌더링하지 않고 원본 마크다운만 훑으므로 빠르다.

check_environment()는 별도로, PDF 빌드용 Playwright Chromium이 설치돼 있지
않은 채로 몇 분짜리 빌드를 돌리다 마지막에야 실패 메시지를 보는 일을 막는다
— `mdbook-binder check`가 코퍼스 점검과 함께 설치 안내까지 한 번에 보여준다.
"""

from __future__ import annotations

import importlib
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


@dataclass
class EnvCheckItem:
    feature: str
    installed: bool
    install_hint: str = ""


def check_environment() -> list[EnvCheckItem]:
    """PDF 빌드·Mermaid 사전 렌더링·웹 에디터 등 선택 기능(extras)의 설치 상태를 점검한다.

    check_corpus()는 원본 마크다운만 훑어 즉시 끝나지만, 이쪽은 Playwright
    Chromium을 실제로 잠깐 띄워봐야 정확히 판단할 수 있어(단순 import 성공만으로는
    브라우저 바이너리가 실제로 존재하는지 알 수 없다) 더 느리다 — 그래서
    check_corpus()와 분리해 호출부(CLI)에서 필요할 때만 명시적으로 부른다.
    """
    return [
        _check_playwright_chromium(),
        _check_module("PDF 병합 (pypdf)", "pypdf", 'pip install "mdbook-binder[pdf]"'),
        _check_module("웹 에디터 (Flask)", "flask", 'pip install "mdbook-binder[editor]"'),
        _check_module("웹 에디터 이미지 처리 (Pillow)", "PIL", 'pip install "mdbook-binder[editor]"'),
    ]


def _check_module(feature: str, module: str, install_hint: str) -> EnvCheckItem:
    try:
        importlib.import_module(module)
    except ImportError:
        return EnvCheckItem(feature, False, install_hint)
    return EnvCheckItem(feature, True)


def _check_playwright_chromium() -> EnvCheckItem:
    feature = "Mermaid 사전 렌더링 · PDF 빌드 (Playwright Chromium)"
    pkg_hint = 'pip install "mdbook-binder[pdf]"  →  python -m playwright install chromium'
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return EnvCheckItem(feature, False, pkg_hint)

    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            browser.close()
    except Exception as exc:
        if "Executable doesn't exist" in str(exc):
            return EnvCheckItem(feature, False, "python -m playwright install chromium")
        return EnvCheckItem(feature, False, f"Playwright Chromium 실행 확인 실패: {exc}")

    return EnvCheckItem(feature, True)


def format_env_report(items: list[EnvCheckItem]) -> str:
    lines: list[str] = ["[선택 기능(extras) 설치 상태]"]
    missing = [item for item in items if not item.installed]
    for item in items:
        if item.installed:
            lines.append(f"  ✅ {item.feature}")
        else:
            lines.append(f"  ⚠️  {item.feature} — 미설치")
            lines.append(f"      → {item.install_hint}")

    if not missing:
        lines.append("")
        lines.append("모든 선택 기능을 사용할 수 있습니다.")

    return "\n".join(lines)
