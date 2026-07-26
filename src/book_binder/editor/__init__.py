"""HTML 편집기.

Lecture_forge의 `editor/html_editor.py`(LectureHTMLEditor → BookHTMLEditor)와
`tools/image_editor.py`(ImageEditor)를 lecture-forge 비의존으로 포크했다.
벡터스토어 기반 유사 이미지 추천(`_search_vector_db` 등, 강의 특화 기능)은
제외했다 — 책 편집에 불필요한 임베딩 의존성을 끌고 오지 않기 위함이며, 대안
이미지는 파일시스템 검색(`_search_filesystem`)만으로 찾는다.

html_book.py가 출력하는 `<section class="chapter-section" id="{slug}">`
구조에만 의존한다 — 다른 어떤 코퍼스 관례(제목 규칙, 로케일 등)에도 결합되지
않는다.
"""
