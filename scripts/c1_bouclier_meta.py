"""Publish and validate C1 bouclier metadata without touching fuel series."""
from __future__ import annotations

from copy import deepcopy

REQUIRED_FUELS = ("Gazole", "SP95")


def _validated_shape(value: object, *, label: str) -> dict:
    if not isinstance(value, dict):
        raise ValueError(f"{label} bouclier metadata absent or invalid")
    for fuel in REQUIRED_FUELS:
        fuel_meta = value.get(fuel)
        if not isinstance(fuel_meta, dict):
            raise ValueError(f"{label} bouclier metadata absent for {fuel}")
        if not isinstance(fuel_meta.get("ranges"), list):
            raise ValueError(f"{label} bouclier ranges invalid for {fuel}")
    return value


def attach_detector_bouclier(meta: dict | None, detector_bouclier: object) -> dict:
    """Return metadata carrying a deep-copied detector result.

    Existing metadata is preserved, but a stale/missing ``bouclier`` field is always
    replaced by the output calculated during the current V2 build.
    """
    detector = _validated_shape(detector_bouclier, label="detector")
    out = deepcopy(meta or {})
    out["bouclier"] = deepcopy(detector)
    return out


def validate_detector_bouclier(meta: dict | None, detector_bouclier: object) -> dict:
    """Fail if published C1 metadata is absent, malformed or stale."""
    detector = _validated_shape(detector_bouclier, label="detector")
    published = _validated_shape((meta or {}).get("bouclier"), label="published")
    if published != detector:
        raise ValueError("published bouclier metadata differs from detector output")
    return published
