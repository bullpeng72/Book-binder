# Book-binder

임의의 마크다운 코퍼스를 검색 가능한 단일 HTML 도서와 PDF(단권/병합)로 변환하고,
결과 HTML을 편집하는 범용 애플리케이션.

`Book_forge/Book`, `Agent-Evaluator/Media/Book`, `Agent-Evaluator/Media/AOO`에
각각 따로 존재하던 `build_book.py`/`build_pdf_chapters.py`(총 ~5,600줄, 사실상
동일 엔진의 사본)를 대체하기 위해 만들어진 독립 저장소다. 세 저장소 중 어느 하나도
이 빌드 엔진을 소유하지 않으며, 전부 이 패키지를 의존성으로 참조한다.

## 설계 원칙

1. **순서 해석은 3단계 우선순위**로 자동 결정된다 — 코드 수정 없이 새 마크다운
   파일이 반영되도록 하는 것이 핵심 목표다.
   1. 명시적 `book.yaml`(`order.manifest` 또는 `order.files`)
   2. `book.yaml`이 없어도 루트에 ` ```toc ` 펜스 매니페스트(Book-forge 목차
      포맷)가 있으면 자동 채택
   3. `Part_<로마숫자>_.../Chapter_<NN>_...` 명명 규칙 감지
   4. 위 전부 실패 시 디렉토리 트리 전체를 자연정렬(natural sort)해 전부 포함 —
      "새 파일이 조용히 누락되는 일"을 구조적으로 없애는 최종 폴백
2. **책마다 다른 값(제목/저자/언어/제외 패턴/콜아웃 마커)은 전부 `book.yaml`로
   외부화** — 렌더링 엔진(`render.py`) 코드는 어떤 코퍼스에도 수정 없이 동작해야
   한다.
3. **섹션 ID는 기본적으로 H1/파일명 slug 자동 생성** — 수작업 매핑 테이블은
   "예쁜 URL을 원할 때만 쓰는 선택적 오버라이드"로 격하한다.
4. HTML 출력은 항상 `<section class="chapter-section" id="{slug}">` 구조를
   지킨다 — 이것이 편집기(`editor/`)가 의존하는 유일한 불변 계약이다.

## 사용법

```bash
book-binder check      <코퍼스_루트>                                     빌드 전 사전 점검
book-binder build html <코퍼스_루트> [--out out.html] [--title ...] [--language ko|en]
book-binder build pdf  <코퍼스_루트> [--merge [이름]] [--out-dir ...]
book-binder edit       <html_경로> [--port 5757] [--out ...] [--no-browser]
```

`check`는 실제로 빌드(HTML 렌더링)하지 않고 원본 마크다운만 훑어 (1) 순서가 몇
순위로 결정됐는지 (2) 같은 제목을 쓰는 챕터가 있는지 (3) 이미지 참조가 끊긴 곳이
있는지를 보여준다 — `Media/Book`을 실전 변환하며 겪은 두 문제(집필 가이드 문서가
챕터로 잘못 포함된 것, 이미지 참조 누락)를 빌드가 끝난 뒤에야 발견했던 경험에서
추가했다. `build html`도 빌드 끝에 누락 이미지 전체를 한 번에 요약 출력한다 —
챕터가 많으면 경고 한 줄이 진행 로그 사이에 묻히기 쉽다.

`build pdf`는 현재 코퍼스 전체(매니페스트가 정한 순서)를 대상으로만 동작한다 —
`build_pdf_chapters.py`가 갖고 있던 "특정 파일/패턴만 지정해 부분 빌드"(모드 2)는
아직 이식하지 않았다([알려진 한계](#알려진-한계) 참고).

## 현재 구현 상태

- [x] `manifest.py` — `BookConfig`(`book.yaml` 로더) + `resolve()`/`resolve_verbose()`
      3단계 우선순위
- [x] `render.py` — `md_to_html`/`inject_mermaid`/`demote_headings` (기존 3사본
      통합, config 주입식 콜아웃/로케일)
- [x] `html_book.py` — 사이드바/검색/base64 이미지 임베드, 섹션 id 충돌 자동 회피,
      누락 이미지 빌드 후 요약
- [x] `pdf_book.py` — `build_pdf_chapters.py`(Playwright 청크 캡처)를 이식,
      개별/`--merge` 단권 둘 다 실제 도서(mermaid 포함)로 검증
- [x] `editor/` — `Lecture_forge`의 `LectureHTMLEditor`/`ImageEditor`를
      lecture-forge 비의존으로 포크(벡터스토어 추천 기능 제외), 섹션 조회·수정·
      삭제·이미지 목록·저장 라운드트립 검증
- [x] `check.py` — 빌드 전 사전 점검(순서 해석 단계·중복 제목·누락 이미지)
- [x] `cli.py` — `check`/`build html`/`build pdf`/`edit` 전부 동작

실제 3권(`Book_forge/Book`, `Media/Book`, `Media/AOO`)을 실전 변환하며 찾은
버그(후주/부록 순서, 로마숫자-숫자 part_no 불일치, 문서 레벨 `<h1>` 부재, 동일
제목 챕터의 섹션 id 충돌)는 전부 수정·회귀 테스트로 고정했고, `Media/Book`은
`book.yaml`(집필 가이드 문서 제외)과 누락 이미지 1건 보강까지 마쳐 실제로
`agent-evaluator-book.html`을 이 도구로 교체했다.

## 알려진 한계

- **부분 빌드 미지원**: `build pdf`/`build html` 모두 코퍼스 전체만 빌드한다 —
  원본 `build_pdf_chapters.py`의 "파일/패턴 지정 부분 변환"(모드 2)은 아직
  없다. 필요해지면 `resolve()`가 반환한 챕터 목록을 CLI에서 필터링하는 방식으로
  추가하면 된다.
- **마크다운 스캐폴딩(정형 스텁 생성) 미포함**: 의도적으로 이번 범위에서
  제외했다(Book-forge 자체 저작 파이프라인과 중복 방지 목적) — 새 챕터 파일은
  손으로 작성해야 한다.
- **`Part_<로마숫자>_...` 명명 규칙 감지(2순위)는 `Appendix/`만 특별 취급**:
  그 외 비-Part 디렉토리(예: 별도 부록 명칭)는 3순위 자연정렬로만 잡힌다 —
  필요하면 `book.yaml`의 `order.files`로 명시하는 게 안전하다.
- **`pdf_book.py`/`editor/`는 자동화된 회귀 테스트가 없다**: 이번 세션에서 실제
  코퍼스로 수동 검증(Flask test client, Playwright 실제 렌더링)은 마쳤지만,
  `manifest.py`(5개)·`html_book.py`(3개)·`check.py`(4개)만큼 pytest 테스트로
  고정되어 있지는 않다.
