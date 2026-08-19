from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
JS = (ROOT / "freshness.js").read_text(encoding="utf-8")


class WeeklyRegionalRankingTests(unittest.TestCase):
    def test_ranking_uses_last_complete_week(self):
        self.assertIn("const end=addDays(start,6);", JS)
        self.assertIn("if(end&&end<=maxDate)chosen=row;", JS)
        self.assertIn("prevOffset:offset-7", JS)

    def test_ranking_uses_weekly_ttc_not_last_daily_value(self):
        self.assertIn("getSeries(ck,key,'w')", JS)
        self.assertIn("v:c1WeeklyTtc(k,ctx.offset,ctx.ck)", JS)
        self.assertIn("prev:c1WeeklyTtc(k,ctx.prevOffset,ctx.ck)", JS)

    def test_trend_arrows_and_corse_label(self):
        self.assertIn("arrow='↗';color='#dc2626'", JS)
        self.assertIn("arrow='↘';color='#16a34a'", JS)
        self.assertIn("item.k==='corse'?'Corse'", JS)
        self.assertNotIn('rank-bar-wrap', JS.split('function installC1WeeklyRanking()', 1)[1].split('function ensureBadge()', 1)[0])

    def test_heading_mentions_week(self):
        self.assertIn("CLASSEMENT · SEMAINE ${c1RankingWeekText(ctx)}", JS)


if __name__ == "__main__":
    unittest.main()
