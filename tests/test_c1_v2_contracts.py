"""P1 regression tests for the C1 V2 publication contract.

These fixtures model failures found by the audit.  They deliberately exercise the
promotion boundary rather than the upstream parser: a malformed candidate must fail closed
even if it somehow reaches the promoter.
"""
from copy import deepcopy
from datetime import date, timedelta
import unittest

import c1_v2_contracts as contracts
import update_data_v2 as core


REGIONS = ["corse", "moy_regions"] + core.REGIONS


def row(off, ttc, region):
    vat = 1.13 if region == "corse" else 1.20
    return [off, round(ttc, 3), round(ttc / vat, 3)]


def payload(last_off=1):
    data = {}
    for short, base in (("G", 1.80), ("S", 1.90)):
        data[short] = {}
        for idx, region in enumerate(REGIONS):
            # Keep the mainland aggregate exactly equal to the 12 regional means.
            ttc = base if region in ("corse", "moy_regions") else base
            data[short][region] = {
                "d": [row(off, ttc, region) for off in range(last_off + 1)],
                "w": [],
                "m": [],
            }
    last_date = str(core.ORIGIN + timedelta(days=last_off))
    data["meta"] = {
        "last_date": last_date,
        "editorial": {
            "Gazole": {"through": last_date},
            "SP95": {"through": last_date},
        },
        "station_audit": {"as_of": last_date},
    }
    return data


def append_day(base, off=2):
    out = deepcopy(base)
    for short, ttc in (("G", 1.81), ("S", 1.91)):
        for region in REGIONS:
            out[short][region]["d"].append(row(off, ttc, region))
    last_date = str(core.ORIGIN + timedelta(days=off))
    out["meta"]["last_date"] = last_date
    out["meta"]["editorial"]["Gazole"]["through"] = last_date
    out["meta"]["editorial"]["SP95"]["through"] = last_date
    out["meta"]["station_audit"]["as_of"] = last_date
    return out


class C1V2CandidateContractTests(unittest.TestCase):
    def setUp(self):
        self.baseline = payload(1)
        self.candidate = append_day(self.baseline, 2)

    def test_valid_append_passes(self):
        contracts.validate_appended_daily_contract(self.baseline, self.candidate)

    def test_rejects_99_eur_litre_for_gazole_and_sp95(self):
        for short in ("G", "S"):
            with self.subTest(fuel=short):
                bad = deepcopy(self.candidate)
                bad[short]["corse"]["d"][-1] = [2, 99.0, 99.0 / 1.13]
                with self.assertRaises(ValueError):
                    contracts.validate_appended_daily_contract(self.baseline, bad)

    def test_rejects_negative_ht_for_gazole_and_sp95(self):
        for short in ("G", "S"):
            with self.subTest(fuel=short):
                bad = deepcopy(self.candidate)
                bad[short]["corse"]["d"][-1][2] = -0.5
                with self.assertRaises(ValueError):
                    contracts.validate_appended_daily_contract(self.baseline, bad)

    def test_rejects_missing_day_in_appended_tail(self):
        bad = append_day(self.baseline, 3)
        with self.assertRaises(ValueError):
            contracts.validate_appended_daily_contract(self.baseline, bad)

    def test_rejects_isolated_series_ahead(self):
        bad = deepcopy(self.candidate)
        bad["S"]["PACA"]["d"].append(row(3, 1.92, "PACA"))
        bad["meta"]["last_date"] = str(core.ORIGIN + timedelta(days=3))
        with self.assertRaises(ValueError):
            contracts.validate_appended_daily_contract(self.baseline, bad)

    def test_rejects_incoherent_mainland_aggregate(self):
        bad = deepcopy(self.candidate)
        bad["G"]["moy_regions"]["d"][-1][1] += 0.20
        with self.assertRaises(ValueError):
            contracts.validate_appended_daily_contract(self.baseline, bad)

    def test_rejects_ht_not_derived_from_ttc(self):
        bad = deepcopy(self.candidate)
        bad["S"]["Normandie"]["d"][-1][2] += 0.05
        with self.assertRaises(ValueError):
            contracts.validate_appended_daily_contract(self.baseline, bad)


class C1V2MetadataContractTests(unittest.TestCase):
    def test_editorial_and_station_audit_must_follow_publication(self):
        good = payload(5)
        contracts.validate_publication_metadata(good)

        for path in (("editorial", "Gazole", "through"), ("editorial", "SP95", "through"), ("station_audit", "as_of")):
            with self.subTest(path=path):
                bad = deepcopy(good)
                node = bad["meta"]
                for key in path[:-1]:
                    node = node[key]
                node[path[-1]] = "2026-08-23"
                with self.assertRaises(ValueError):
                    contracts.validate_publication_metadata(bad)

    def test_bouclier_contract_requires_complete_evaluation_fields(self):
        last_date = "2026-09-06"
        meta = {
            "last_date": last_date,
            "bouclier": {
                "Gazole": {
                    "ranges": [{"d1": "2026-03-20", "d2": "2026-04-07"}],
                    "current_active": False,
                    "current_active_since": None,
                    "current_cap": 2.25,
                    "evaluated_through": last_date,
                    "latest_total_stations": 40,
                    "latest_non_total_stations": 80,
                    "latest_at_cap_count": 0,
                    "latest_non_total_p75": 2.10,
                    "rule": {"definition": "rule"},
                },
                "SP95": {
                    "ranges": [{"d1": "2026-03-20", "d2": "2026-04-07"}],
                    "current_active": False,
                    "current_active_since": None,
                    "current_cap": 1.99,
                    "evaluated_through": last_date,
                    "latest_total_stations": 35,
                    "latest_non_total_stations": 75,
                    "latest_at_cap_count": 0,
                    "latest_non_total_p75": 1.90,
                    "rule": {"definition": "rule"},
                },
            },
        }
        contracts.validate_bouclier_contract(meta)
        for fuel, field in (("Gazole", "evaluated_through"), ("Gazole", "current_cap"), ("SP95", "latest_non_total_stations"), ("SP95", "rule")):
            with self.subTest(fuel=fuel, field=field):
                bad = deepcopy(meta)
                bad["bouclier"][fuel].pop(field)
                with self.assertRaises(ValueError):
                    contracts.validate_bouclier_contract(bad)


if __name__ == "__main__":
    unittest.main()
