"""이미지 파일 → base64 data URI 인코딩 공용 유틸.

html_book.py(최초 빌드)와 editor/(이미지 추가·교체 후 저장)가 같은 인코딩
규칙을 공유해야, 편집기로 저장한 HTML도 최초 빌드본과 동일하게 이미지가
파일 하나에 인라인 임베드된 상태를 유지한다.
"""

from __future__ import annotations

import base64
import mimetypes
from pathlib import Path

_MIME_OVERRIDES = {".svg": "image/svg+xml"}


def image_to_data_uri(path: Path) -> str:
    mime = _MIME_OVERRIDES.get(path.suffix.lower()) or mimetypes.guess_type(path.name)[0]
    mime = mime or "application/octet-stream"
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{encoded}"
