"""사이드바/제목 등 강조색을 한 번에 바꾸는 색상 테마 프리셋.

레이아웃·폰트는 그대로 두고 강조색 3개(`--primary`/`--primary-light`/`--accent`)만
바꾸는 "메뉴 색 고르기" 수준의 가벼운 커스터마이징이다. 사이드바 배경이
`--primary` 위에 흰 글자를 얹으므로(`html_book.css`의 `#sidebar`), 프리셋은
전부 흰 글자와 대비가 충분한 톤으로만 골랐다 — 임의의 hex를 받으면 밝은
색을 골랐을 때 글자가 안 보이는 사고가 나기 쉽다.
"""

from __future__ import annotations

# name: (primary, primary-light, accent)
THEMES: dict[str, tuple[str, str, str]] = {
    "purple": ("#4527a0", "#5e35b1", "#00897b"),  # 기본값 (html_book.css 원래 배색)
    "blue": ("#1565c0", "#1e88e5", "#00897b"),
    "green": ("#2e7d32", "#43a047", "#00897b"),
    "teal": ("#00695c", "#00897b", "#5e35b1"),
    "red": ("#c62828", "#e53935", "#00695c"),
    "orange": ("#e65100", "#f57c00", "#00695c"),
    "gray": ("#37474f", "#546e7a", "#00897b"),
}


def theme_css(name: str) -> str:
    """`name` 테마의 강조색으로 `:root` 커스텀 프로퍼티를 덮어쓰는 CSS 조각을 반환한다.

    원본 `html_book.css` 뒤에 그대로 이어 붙이기만 하면 된다 — 같은 선택자
    (`:root`)라 `!important` 없이 CSS 캐스케이드(나중 규칙이 이긴다)만으로
    충분하다.

    CLI(`--color`)는 `click.Choice`가 이미 걸러주지만, book.yaml의 `color:`는
    그 검증을 거치지 않고 곧장 여기로 들어오므로 오타를 KeyError가 아니라
    선택 가능한 이름 목록을 보여주는 메시지로 알려준다.
    """
    key = name.lower()
    if key not in THEMES:
        valid = ", ".join(sorted(THEMES))
        raise ValueError(f"알 수 없는 색상 테마: {name!r} (선택 가능: {valid})")
    primary, primary_light, accent = THEMES[key]
    return (
        f"/* ── color theme: {key} ── */\n"
        f":root {{ --primary: {primary}; --primary-light: {primary_light}; --accent: {accent}; }}"
    )
