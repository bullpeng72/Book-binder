"""pdf_book.py의 페이지 경계 계산 순수 함수 회귀 테스트.

`_merge_bands`/`_is_occupied`/`_nearest_safe_y`/`_chunk_boundaries`는 Mermaid
다이어그램을 PDF 페이지 경계에 맞춰 청크로 나누는 핵심 로직이다(pdf_book.py
모듈 docstring 참고). Playwright 브라우저 없이도 순수 계산만으로 테스트
가능한데, 최근 커밋 두 개(청크가 페이지 절반도 못 채운 채 다음 페이지로
밀리는 문제, 도형 한가운데가 잘리는 문제)가 정확히 이 로직의 버그를 고친
자리라 회귀 테스트로 고정해둔다.
"""

from mdbook_binder.pdf_book import (
    _chunk_boundaries,
    _is_occupied,
    _merge_bands,
    _nearest_safe_y,
)


class TestMergeBands:
    def test_empty_input(self):
        assert _merge_bands([]) == []

    def test_disjoint_bands_stay_separate(self):
        assert _merge_bands([(0, 5), (10, 15)]) == [(0, 5), (10, 15)]

    def test_overlapping_bands_merge(self):
        assert _merge_bands([(0, 10), (5, 15)]) == [(0, 15)]

    def test_touching_bands_merge(self):
        """끝점이 정확히 맞닿는 경우(s <= 이전 끝)도 하나로 합쳐야 한다."""
        assert _merge_bands([(0, 5), (5, 10)]) == [(0, 10)]

    def test_unsorted_input_is_sorted_before_merging(self):
        assert _merge_bands([(10, 20), (0, 5), (4, 12)]) == [(0, 20)]


class TestIsOccupied:
    def test_interior_point_is_occupied(self):
        assert _is_occupied(5, [(0, 10)]) is True

    def test_exact_boundary_is_not_occupied(self):
        """경계값(s, e) 자체는 점유 구간에 포함하지 않는다(엄격한 부등호) —
        `_nearest_safe_y`가 밴드 가장자리를 안전한 절단 지점으로 쓸 수 있으려면
        이 경계값이 '비어 있음'으로 취급돼야 한다."""
        assert _is_occupied(0, [(0, 10)]) is False
        assert _is_occupied(10, [(0, 10)]) is False

    def test_point_outside_any_band_is_not_occupied(self):
        assert _is_occupied(15, [(0, 10)]) is False


class TestNearestSafeY:
    def test_returns_target_unchanged_when_already_free(self):
        assert _nearest_safe_y(50, [(0, 10)], 0, 100) == 50

    def test_clamps_target_into_lo_hi_range_first(self):
        assert _nearest_safe_y(500, [], 0, 100) == 100
        assert _nearest_safe_y(-50, [], 0, 100) == 0

    def test_shifts_away_from_occupied_band_toward_lo(self):
        """target이 도형 한가운데면, 검색 범위(lo~target) 안에서 가장 가까운
        빈 지점으로 물러나야 한다 — 위쪽(작은 y)으로만 물러나고 hi(페이지
        경계) 너머로는 절대 넘어가지 않는다."""
        safe = _nearest_safe_y(1000, [(950, 1050)], 400, 1000)
        assert safe == 950.0
        assert not _is_occupied(safe, [(950, 1050)])

    def test_falls_back_to_target_when_entire_range_occupied(self):
        """lo~hi 전체가 점유돼 안전한 지점을 못 찾으면 target을 그대로 반환한다
        (호출부가 이 경우를 별도로 감내함)."""
        assert _nearest_safe_y(5, [(0, 10)], 0, 10) == 5


class TestChunkBoundaries:
    def test_diagram_fitting_in_remaining_space_is_single_chunk(self):
        assert _chunk_boundaries(th=100, bands_raw=[], page_h=1000, remaining_first=150) == [
            0.0,
            100.0,
        ]

    def test_tiny_remaining_space_is_skipped_in_favor_of_next_page(self):
        """페이지 하단에 15% 미만만 남았으면 그 자투리를 억지로 쓰지 않고
        페이지 한 장 분량(page_h) 전체를 기준으로 다시 판단해야 한다."""
        # remaining_first=100은 page_h(1000)의 15% 미만이므로 무시되고
        # page_h 전체(1000) 기준으로 판단 → th(50)가 한 청크에 들어간다.
        assert _chunk_boundaries(th=50, bands_raw=[], page_h=1000, remaining_first=100) == [
            0.0,
            50.0,
        ]

    def test_multi_page_split_without_bands_lands_exactly_on_page_boundaries(self):
        boundaries = _chunk_boundaries(th=2500, bands_raw=[], page_h=1000, remaining_first=1000)
        assert boundaries == [0.0, 1000.0, 2000.0, 2500.0]

    def test_boundary_never_cuts_through_the_middle_of_a_shape(self):
        """실측으로 확인됐던 회귀: 청크 경계가 도형/라벨 밴드 한가운데를 지나면
        박스나 텍스트가 반토막나 보인다. 밴드가 페이지 경계에 걸쳐 있을 때
        경계가 밴드 밖으로 밀려나는지 확인한다."""
        boundaries = _chunk_boundaries(
            th=2000, bands_raw=[(950, 1050)], page_h=1000, remaining_first=1000
        )
        interior_boundaries = boundaries[1:-1]
        assert interior_boundaries, "테스트 시나리오가 실제로 중간 경계를 만들어내야 한다"
        for y in interior_boundaries:
            assert not _is_occupied(y, [(950, 1050)])

    def test_chunk_never_overshoots_its_page_budget(self):
        """청크 하나가 페이지 경계를 넘으면 break-inside:avoid가 있어도 이미지
        자체가 잘려버린다(모듈 docstring 참고) — 각 경계는 목표 지점(budget 누적)
        이전에서만 잡혀야 한다."""
        boundaries = _chunk_boundaries(
            th=3000, bands_raw=[(1900, 2100)], page_h=1000, remaining_first=1000
        )
        budget_ceiling = 0.0
        remaining = [1000.0] + [1000.0] * 10  # 첫 청크 1000, 이후 매 페이지 1000
        for i in range(1, len(boundaries)):
            budget_ceiling += remaining[i - 1]
            assert boundaries[i] <= budget_ceiling + 1e-9
