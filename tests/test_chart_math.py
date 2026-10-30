"""Headless tests for the chart geometry helpers."""
import math

import pytest

from kse.presentation.chart_math import (
    compact_number, donut_spans, label_step, nice_ticks, slot_at, slot_layout, visible_label_indices,
)


class TestNiceTicks:
    def test_old_bug_case_gives_round_ticks(self):
        ticks, top = nice_ticks(3584)          # old chart: 1,195 / 2,389 / 3,584
        assert ticks == [0, 1000, 2000, 3000, 4000] and top == 4000

    @pytest.mark.parametrize("m", [0.3, 1, 7, 99, 100, 101, 12_345, 987_654_321])
    def test_covers_max_and_is_monotonic(self, m):
        ticks, top = nice_ticks(m)
        assert top >= m - 1e-9 and ticks[0] == 0 and top == ticks[-1]
        assert all(b > a for a, b in zip(ticks, ticks[1:]))
        assert 2 <= len(ticks) <= 8

    def test_empty_or_bad_input(self):
        for bad in (0, -5, float("nan"), float("inf")):
            assert nice_ticks(bad) == ([0.0, 1.0], 1.0)

    def test_integer_axis_never_fractional(self):
        ticks, _ = nice_ticks(3, integer=True)
        assert all(float(t).is_integer() for t in ticks)


class TestCompactNumber:
    def test_values(self):
        assert compact_number(950) == "950"
        assert compact_number(1_250) == "1.25K"
        assert compact_number(3_000_000) == "3M"
        assert compact_number(-2_500_000) == "-2.5M"
        assert compact_number(2.5) == "2.5"

    def test_arabic_suffix(self):
        assert compact_number(2_000_000, arabic=True) == "2 مليون"


class TestSlots:
    def test_bars_are_capped_and_centered(self):
        slots = slot_layout(2, 50, 800)
        assert all(s.bar_w == 64 for s in slots)          # no giant blocks
        for s in slots:
            assert math.isclose(s.bar_x + s.bar_w / 2, s.x + s.width / 2)

    def test_many_bars_shrink_but_stay_visible(self):
        slots = slot_layout(60, 0, 600)
        assert all(s.bar_w >= 4 for s in slots)

    def test_hit_test_matches_paint_geometry(self):
        """Regression: hover used a different left margin than painting."""
        slots = slot_layout(5, 40, 500)
        for s in slots:
            assert slot_at(slots, s.bar_x + s.bar_w / 2) == s.index
        assert slot_at(slots, 10) is None and slot_at(slots, 540) is None

    def test_rtl_mirrors_order(self):
        ltr = slot_layout(4, 0, 400)
        rtl = slot_layout(4, 0, 400, rtl=True)
        assert ltr[0].x < ltr[-1].x and rtl[0].x > rtl[-1].x
        assert sorted(s.x for s in ltr) == sorted(s.x for s in rtl)

    def test_degenerate(self):
        assert slot_layout(0, 0, 100) == [] and slot_layout(3, 0, 0) == []


class TestLabels:
    def test_step_prevents_overlap(self):
        assert label_step(100, 60) == 1
        assert label_step(30, 60) == 3

    def test_newest_always_visible(self):
        idx = visible_label_indices(10, 3)
        assert idx == [0, 3, 6, 9] and idx[-1] == 9
        assert visible_label_indices(5, 1) == [0, 1, 2, 3, 4]
        assert visible_label_indices(0, 1) == []


class TestDonut:
    def test_spans_sum_to_full_ring_minus_gaps(self):
        spans = donut_spans([3, 1, 0, 4], gap_deg=2)
        assert spans[2][1] == 0
        assert math.isclose(sum(s for _, s in spans), 360 - 3 * 2)
        starts = [a for a, s in spans if s > 0]
        assert starts == sorted(starts)

    def test_single_slice_is_full_circle(self):
        assert donut_spans([0, 5, 0])[1] == (0.0, 360.0)

    def test_all_zero(self):
        assert donut_spans([0, 0]) == [(0.0, 0.0), (0.0, 0.0)]
