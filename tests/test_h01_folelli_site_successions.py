import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config" / "total_corse_stations.json"


def test_folelli_ids_are_preserved_without_aliasing_price_history():
    cfg = json.loads(CONFIG.read_text(encoding="utf-8"))

    # H-01: do not erase administrative history. 20213008 is the current
    # TotalEnergies id observed at the same physical coordinates as 20213003;
    # older ids remain explicitly historical rather than being rewritten away.
    assert "historical_aliases" not in cfg
    assert "20213008" in cfg["stations"]
    assert "20213007" not in cfg["stations"]

    historical = set(cfg["historical_total_ids"])
    assert {"20213003", "20213006", "20213007"} <= historical
    assert "20213008" not in historical

    successions = cfg["site_successions"]
    folelli = next(
        row for row in successions
        if row.get("predecessor_id") == "20213003"
        and row.get("successor_id") == "20213008"
    )
    assert folelli["relation"] == "same_physical_site_successor_probable"
    assert folelli["price_transfer"] is False
    assert folelli["cause_of_id_change"] == "unknown"
    assert folelli["evidence"]["same_coordinates"] is True
    assert folelli["evidence"]["predecessor_last_price_date"] == "2025-12-23"
    assert folelli["evidence"]["successor_first_price_date"] == "2026-09-04"


def test_site_succession_metadata_cannot_merge_station_price_series():
    # The documentary succession metadata must never be read by either price
    # builder. Price state remains keyed strictly by the official station id.
    for relative in (
        "scripts/update_data_v2.py",
        "scripts/build_c1_v2_candidate.py",
    ):
        source = (ROOT / relative).read_text(encoding="utf-8")
        assert "site_successions" not in source
        assert "successor_id" not in source
