#!/usr/bin/env python3
"""Render the human-readable GitHub Actions summary from a validated candidate data.json."""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def signed(v):
    return "—" if v is None else f"{v:+.1f}"


def decimal(v, digits=2):
    return "—" if v is None else f"{v:.{digits}f}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", default="data-candidate.json")
    args = ap.parse_args()

    d = json.loads(Path(args.input).read_text(encoding="utf-8"))
    m = d["meta"]
    print(f"## Observatoire A4C — {m['last_date']}")

    for fuel in ("Gazole", "SP95"):
        b = m["bouclier"][fuel]
        e = m["editorial"][fuel]
        status = "contraignant" if b["current_active"] else "non contraignant"
        share = b.get("latest_near_share")
        share_txt = "—" if share is None else f"{100 * share:.0f}%"
        print(f"\n### {fuel}")
        print(f"- Écart HT moyen depuis janvier : **{signed(e['observed_ytd_gap'])} c€/L**")
        print(f"- Hors toute action TotalEnergies : **{signed(e['outside_total_action_gap'])} c€/L**")
        print(f"- Pendant les actions TotalEnergies : **{signed(e['during_total_action_gap'])} c€/L**")
        print(f"- Plafond suivi : **{decimal(b.get('current_cap'), 2)} €/L**, actuellement **{status}**")
        print(f"- Total proches du plafond : **{share_txt}** ({b.get('latest_total_stations', '—')} stations suivies)")
        print(f"- 75e percentile non-Total Corse : **{decimal(b.get('latest_non_total_p75'), 3)} €/L**")

    print("\n## Nettoyage des stations corses")
    audit = m["station_audit"]
    threshold = audit.get("max_station_inactive_days", audit.get("max_ffill_days"))
    print(
        f"État au **{audit['as_of']}**. Une station reste active pendant **{threshold} jours** "
        "après sa dernière déclaration Gazole/SP95 ou son dernier événement de rupture."
    )
    print(
        "Un prix de carburant inchangé peut être plus ancien : il reste retenu tant que la "
        "station reste active, que le dernier prix est valide et qu'aucune rupture n'est ouverte."
    )

    for fuel in ("Gazole", "SP95"):
        a = audit["fuels"][fuel]
        print(f"\n### {fuel}")
        print(f"- Séries station-carburant connues (stocks N-1/N) : **{a['known_station_fuel_series']}**")
        print(f"- Ayant déclaré au moins une fois cette année : **{a['declared_current_year']}**")
        print(f"- Retenues dans la moyenne du dernier jour : **{a['retained']}**")
        print(
            f"- Retenues malgré un prix de plus de {threshold} jours car station active : "
            f"**{a.get('retained_old_price_active_station', 0)}**"
        )
        print(f"- Exclues car station inactive : **{a.get('excluded_inactive_station', a.get('excluded_stale', 0))}**")
        print(f"- Exclues car rupture du carburant encore active : **{a.get('excluded_active_rupture', 0)}**")
        print(f"- Exclues car dernier prix invalide : **{a['excluded_invalid_latest']}**")
        print(f"- Exclues faute d'état antérieur exploitable : **{a['excluded_no_prior']}**")

        old_ids = a.get("retained_old_price_active_station_ids", [])
        if old_ids:
            ids = ", ".join(x["station_id"] for x in old_ids[:20])
            suffix = " …" if len(old_ids) > 20 else ""
            print(f"- IDs prix ancien / station active (20 max) : `{ids}{suffix}`")

        inactive_ids = a.get("excluded_inactive_station_ids", a.get("excluded_stale_ids", []))
        if inactive_ids:
            ids = ", ".join(x["station_id"] for x in inactive_ids[:20])
            suffix = " …" if len(inactive_ids) > 20 else ""
            print(f"- IDs stations inactives (20 max) : `{ids}{suffix}`")

        rupture_ids = a.get("excluded_active_rupture_ids", [])
        if rupture_ids:
            ids = ", ".join(x["station_id"] for x in rupture_ids[:20])
            suffix = " …" if len(rupture_ids) > 20 else ""
            print(f"- IDs en rupture active (20 max) : `{ids}{suffix}`")

        if a["excluded_invalid_ids"]:
            ids = ", ".join(x["station_id"] for x in a["excluded_invalid_ids"])
            print(f"- IDs avec dernier prix invalide : `{ids}`")

    print("\n### Garde-fous de publication")
    g = audit["guardrails"]
    print(f"- Minimum retenu : Gazole **{g['minimum_retained']['Gazole']}**, SP95 **{g['minimum_retained']['SP95']}** stations.")
    print(f"- Baisse maximale tolérée par rapport au dernier audit : **{100 * g['maximum_retained_drop_vs_previous_audit']:.0f}%**.")
    print(f"- Part maximale de derniers prix invalides : **{100 * g['maximum_invalid_latest_share']:.0f}%**.")


if __name__ == "__main__":
    main()
