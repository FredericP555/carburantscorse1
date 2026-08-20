from datetime import date, datetime

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import update_data_v2 as core


def test_old_unchanged_price_remains_eligible_while_station_is_active():
    day = date(2026, 8, 19)
    price_ts = datetime(2026, 3, 10, 12, 0)
    station_activity = datetime(2026, 8, 10, 9, 0)

    assert (day - price_ts.date()).days > core.MAX_STATION_INACTIVE_DAYS
    assert core.fuel_value_eligible(price_ts, 1.99, station_activity, [], day)


def test_station_activity_threshold_is_inclusive_at_45_days():
    day = date(2026, 8, 19)
    assert core.station_active(datetime(2026, 7, 5, 12, 0), day)
    assert not core.station_active(datetime(2026, 7, 4, 12, 0), day)


def test_inactive_station_excludes_even_recent_last_fuel_price():
    day = date(2026, 8, 19)
    price_ts = datetime(2026, 7, 10, 12, 0)
    station_activity = datetime(2026, 7, 4, 12, 0)

    assert not core.fuel_value_eligible(price_ts, 1.99, station_activity, [], day)


def test_active_rupture_excludes_fuel_without_destroying_last_price():
    day = date(2026, 8, 19)
    price_ts = datetime(2026, 3, 10, 12, 0)
    station_activity = datetime(2026, 8, 18, 9, 0)
    open_rupture = [(datetime(2026, 8, 15, 8, 0), None)]

    assert not core.fuel_value_eligible(
        price_ts, 1.99, station_activity, open_rupture, day
    )


def test_closed_rupture_allows_previous_unchanged_price_to_resume():
    day = date(2026, 8, 19)
    price_ts = datetime(2026, 3, 10, 12, 0)
    station_activity = datetime(2026, 8, 18, 9, 0)
    closed_rupture = [
        (datetime(2026, 8, 15, 8, 0), datetime(2026, 8, 18, 11, 0))
    ]

    assert core.fuel_value_eligible(
        price_ts, 1.99, station_activity, closed_rupture, day
    )


def test_invalid_latest_price_is_excluded():
    day = date(2026, 8, 19)
    assert not core.fuel_value_eligible(
        datetime(2026, 8, 18, 12, 0),
        None,
        datetime(2026, 8, 18, 12, 0),
        [],
        day,
    )
