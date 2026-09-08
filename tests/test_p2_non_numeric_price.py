from __future__ import annotations

import io
import unittest
import zipfile
from unittest.mock import patch

from scripts import update_data_v2 as core


def _zip_xml(xml: str) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("PrixCarburants_annuel.xml", xml)
    return buf.getvalue()


class NonNumericPriceInvalidationTests(unittest.TestCase):
    def test_non_numeric_declaration_invalidates_previous_price_state(self):
        raw = _zip_xml(
            """<?xml version='1.0' encoding='UTF-8'?>
            <pdv_liste>
              <pdv id='20000001' cp='20200' pop='R'>
                <prix nom='Gazole' maj='2026-09-01T10:00:00' valeur='1.800'/>
                <prix nom='Gazole' maj='2026-09-02T10:00:00' valeur='abc'/>
              </pdv>
            </pdv_liste>
            """
        )
        with patch.object(core, "download", return_value=raw):
            parsed = core.parse_year(2026)

        updates = parsed[("20000001", "corse", "Gazole")]
        self.assertEqual(len(updates), 2)
        self.assertEqual(updates[0][1], 1.8)
        self.assertIsNone(updates[1][1])

    def test_missing_numeric_value_also_invalidates_when_timestamp_is_valid(self):
        raw = _zip_xml(
            """<?xml version='1.0' encoding='UTF-8'?>
            <pdv_liste>
              <pdv id='20000002' cp='20200' pop='R'>
                <prix nom='SP95' maj='2026-09-01T10:00:00' valeur='1.900'/>
                <prix nom='SP95' maj='2026-09-02T10:00:00'/>
              </pdv>
            </pdv_liste>
            """
        )
        with patch.object(core, "download", return_value=raw):
            parsed = core.parse_year(2026)

        updates = parsed[("20000002", "corse", "SP95")]
        self.assertEqual(len(updates), 2)
        self.assertEqual(updates[0][1], 1.9)
        self.assertIsNone(updates[1][1])


if __name__ == "__main__":
    unittest.main()
