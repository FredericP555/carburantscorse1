"""Regression tests for audit finding C1-03.

An active shield must be backed by an effective range covering the evaluated day,
with a matching active-since date and cap phase. An inactive fuel may legitimately
have no effective range at all.
"""
from copy import deepcopy
import unittest

import c1_v2_contracts as contracts


LAST_DATE = "2026-09-06"


def fuel_node(fuel: str) -> dict:
    cap = 2.25 if fuel == "Gazole" else 1.99
    return {
        "ranges": [],
        "phases": [],
        "current_active": False,
        "current_active_since": None,
        "current_cap": cap,
        "evaluated_through": LAST_DATE,
        "latest_total_stations": 40,
        "latest_non_total_stations": 80,
        "latest_at_cap_count": 0,
        "latest_non_total_p75": cap + 0.05,
        "rule": {"definition": "test rule"},
    }


def metadata() -> dict:
    return {
        "last_date": LAST_DATE,
        "bouclier": {
            "Gazole": fuel_node("Gazole"),
            "SP95": fuel_node("SP95"),
        },
    }


def activate_gazole(meta: dict, start: str = "2026-09-01", end: str = LAST_DATE) -> None:
    node = meta["bouclier"]["Gazole"]
    node["ranges"] = [{"d1": start, "d2": end}]
    node["phases"] = [{
        "d1": start,
        "d2": end,
        "cap": 2.25,
        "phase_id": f"Gazole:{start}:2.250",
    }]
    node["current_active"] = True
    node["current_active_since"] = start
    node["current_cap"] = 2.25
    node["latest_at_cap_count"] = 1


class C103BouclierActiveInvariantTests(unittest.TestCase):
    def test_inactive_empty_ranges_and_phases_are_legitimate(self):
        contracts.validate_bouclier_contract(metadata())

    def test_active_without_covering_range_is_rejected(self):
        bad = metadata()
        node = bad["bouclier"]["Gazole"]
        node["current_active"] = True
        node["current_active_since"] = "2026-09-01"
        node["latest_at_cap_count"] = 1
        with self.assertRaises(ValueError):
            contracts.validate_bouclier_contract(bad)

    def test_active_range_must_cover_evaluated_day(self):
        bad = metadata()
        activate_gazole(bad, start="2026-09-01", end="2026-09-05")
        with self.assertRaises(ValueError):
            contracts.validate_bouclier_contract(bad)

    def test_active_since_must_match_covering_range_start(self):
        bad = metadata()
        activate_gazole(bad)
        bad["bouclier"]["Gazole"]["current_active_since"] = "2026-09-02"
        with self.assertRaises(ValueError):
            contracts.validate_bouclier_contract(bad)

    def test_current_cap_must_match_covering_phase(self):
        bad = metadata()
        activate_gazole(bad)
        bad["bouclier"]["Gazole"]["current_cap"] = 2.09
        with self.assertRaises(ValueError):
            contracts.validate_bouclier_contract(bad)

    def test_inactive_state_cannot_cover_evaluated_day(self):
        bad = metadata()
        activate_gazole(bad)
        bad["bouclier"]["Gazole"]["current_active"] = False
        bad["bouclier"]["Gazole"]["current_active_since"] = None
        bad["bouclier"]["Gazole"]["latest_at_cap_count"] = 0
        with self.assertRaises(ValueError):
            contracts.validate_bouclier_contract(bad)


if __name__ == "__main__":
    unittest.main()
