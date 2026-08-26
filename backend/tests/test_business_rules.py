"""Unit tests for app/services/business_rules.py — pure-function checks,
no network, no database (weather flagging is tested separately below with
weather_service monkeypatched, since it's the one async external-dependent
step)."""

from __future__ import annotations

from datetime import date

import pytest

from app.services import business_rules as br


def test_haversine_km_same_point_is_zero() -> None:
    assert br.haversine_km(27.17, 78.04, 27.17, 78.04) == pytest.approx(0.0, abs=1e-6)


def test_haversine_km_agra_to_delhi_is_roughly_correct() -> None:
    # Taj Mahal (Agra) to India Gate (Delhi) is ~200km — sanity range check,
    # not an exact-value assertion (haversine is an approximation anyway).
    km = br.haversine_km(27.1751, 78.0421, 28.6129, 77.2295)
    assert 160 <= km <= 230


def test_compute_budget_summary_within_tolerance_not_flagged() -> None:
    items = [{"estimated_cost": 5000}, {"estimated_cost": 4900}]  # 9900 total
    summary = br.compute_budget_summary(items, planned_budget=10000)
    assert summary["over_budget"] is False
    assert summary["estimated_total"] == 9900


def test_compute_budget_summary_at_111_percent_is_flagged() -> None:
    items = [{"estimated_cost": 11100}]
    summary = br.compute_budget_summary(items, planned_budget=10000)
    assert summary["over_budget"] is True


def test_compute_budget_summary_at_109_percent_not_flagged() -> None:
    items = [{"estimated_cost": 10900}]
    summary = br.compute_budget_summary(items, planned_budget=10000)
    assert summary["over_budget"] is False


def test_compute_budget_summary_no_planned_budget_never_flags() -> None:
    items = [{"estimated_cost": 999999}]
    summary = br.compute_budget_summary(items, planned_budget=None)
    assert summary["over_budget"] is False


def test_check_item_overlaps_detects_overlap() -> None:
    by_day = {
        1: [
            {
                "poi_name": "A",
                "planned_start": "09:00",
                "planned_end": "11:00",
                "sequence_order": 1,
            },
            {
                "poi_name": "B",
                "planned_start": "10:00",
                "planned_end": "12:00",
                "sequence_order": 2,
            },
        ]
    }
    conflicts = br.check_item_overlaps(by_day)
    assert len(conflicts) == 1
    assert "B" in conflicts[0]


def test_check_item_overlaps_no_conflict_when_sequential() -> None:
    by_day = {
        1: [
            {
                "poi_name": "A",
                "planned_start": "09:00",
                "planned_end": "11:00",
                "sequence_order": 1,
            },
            {
                "poi_name": "B",
                "planned_start": "11:30",
                "planned_end": "13:00",
                "sequence_order": 2,
            },
        ]
    }
    assert br.check_item_overlaps(by_day) == []


def test_check_travel_time_conflicts_flags_insufficient_buffer() -> None:
    by_day = {
        1: [
            {
                "poi_name": "Taj Mahal",
                "poi_lat": 27.1751,
                "poi_lng": 78.0421,
                "planned_end": "11:00",
                "sequence_order": 1,
            },
            {
                "poi_name": "India Gate",
                "poi_lat": 28.6129,
                "poi_lng": 77.2295,
                "planned_start": "11:30",
                "sequence_order": 2,
            },
        ]
    }
    conflicts = br.check_travel_time_conflicts(by_day)
    assert len(conflicts) == 1
    assert "India Gate" in conflicts[0]


def test_check_travel_time_conflicts_ok_when_nearby() -> None:
    by_day = {
        1: [
            {
                "poi_name": "A",
                "poi_lat": 27.1751,
                "poi_lng": 78.0421,
                "planned_end": "11:00",
                "sequence_order": 1,
            },
            {
                "poi_name": "B",
                "poi_lat": 27.18,
                "poi_lng": 78.05,
                "planned_start": "11:15",
                "sequence_order": 2,
            },
        ]
    }
    assert br.check_travel_time_conflicts(by_day) == []


def test_apply_opening_hours_check_unknown_hours_means_verify() -> None:
    assert br.apply_opening_hours_check({"poi_opening_hours": None}) is True


def test_apply_opening_hours_check_known_hours_means_no_verify() -> None:
    assert br.apply_opening_hours_check({"poi_opening_hours": {"mon": ["09:00-18:00"]}}) is False


def test_compute_planned_end_adds_duration() -> None:
    assert br.compute_planned_end("09:00", 90) == "10:30"


def test_compute_planned_end_wraps_past_midnight() -> None:
    assert br.compute_planned_end("23:30", 60) == "00:30"


def test_compute_planned_end_missing_inputs_returns_none() -> None:
    assert br.compute_planned_end(None, 60) is None
    assert br.compute_planned_end("09:00", None) is None


async def test_apply_weather_flags_sets_flag_when_adverse(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_check(lat: float, lng: float, date_iso: str) -> bool | None:
        return True

    monkeypatch.setattr(br.weather_service, "check_adverse_weather", fake_check)

    by_day = {1: [{"poi_category": "nature", "poi_lat": 1.0, "poi_lng": 2.0}]}
    await br.apply_weather_flags(by_day, {1: date(2026, 10, 10)})

    assert by_day[1][0]["weather_flag"] is True
    assert by_day[1][0]["weather_alternative_suggestion"] is not None


async def test_apply_weather_flags_skips_non_outdoor_categories(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_check(lat: float, lng: float, date_iso: str) -> bool | None:
        raise AssertionError("should never be called for a non-outdoor category")

    monkeypatch.setattr(br.weather_service, "check_adverse_weather", fake_check)

    by_day = {1: [{"poi_category": "restaurant", "poi_lat": 1.0, "poi_lng": 2.0}]}
    await br.apply_weather_flags(by_day, {1: date(2026, 10, 10)})
    assert by_day[1][0].get("weather_flag") is None


async def test_apply_weather_flags_unknown_forecast_does_not_flag(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_check(lat: float, lng: float, date_iso: str) -> bool | None:
        return None

    monkeypatch.setattr(br.weather_service, "check_adverse_weather", fake_check)

    by_day = {1: [{"poi_category": "heritage", "poi_lat": 1.0, "poi_lng": 2.0}]}
    await br.apply_weather_flags(by_day, {1: date(2026, 10, 10)})
    assert by_day[1][0].get("weather_flag") is None
