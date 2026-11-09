"""Run with python -m unittest -v. No extra test packages required."""
import unittest

import pandas as pd

from prepare_data import BOROUGHS, FIELDS, clean_restaurants, read_raw, DATA
from app import (app, bar_figure, create_app, cuisine_summary, heatmap_figure,
                 load_data, scatter_figure, select_state)


class CleaningTests(unittest.TestCase):
    def setUp(self):
        # Deliberately repeated violations, old grades, missing info, and no-grade cases.
        rows = [
            ["1", "Brooklyn", "Chinese", "2025-01-01", "A"],
            ["1", "Brooklyn", "Chinese", "2025-01-01", "A"],
            ["1", "Queens", "Thai", "2025-02-01", "B"],
            ["1", "", "", "2025-03-01", "N"],
            ["2", "Brooklyn", "Chinese", "1900-01-01", ""],
            ["3", "Brooklyn", "Chinese", "2025-02-01", "A"],
            ["4", "Brooklyn", "", "not a date", "A"],
            ["5", "0", "Pizza", "2025-02-01", "A"],
            ["", "Queens", "Thai", "2025-02-01", "A"],
            ["6", "Bronx", "Pizza", "2025-02-01", "A"],
            ["6", "Bronx", "Pizza", "2025-02-01", "C"],
            ["7", "Manhattan", "Thai", "2027-01-01", "A"],
        ]
        self.clean, self.audit = clean_restaurants(pd.DataFrame(rows, columns=FIELDS), "2026-11-09")

    def test_unique_restaurants_and_independent_latest_grade(self):
        self.assertEqual(len(self.clean), 6)
        self.assertTrue(self.clean.CAMIS.is_unique)
        one = self.clean.set_index("CAMIS").loc["1"]
        self.assertEqual((one.borough, one.cuisine, one.grade), ("Queens", "Thai", "B"))
        self.assertEqual(str(one.graded_inspection_date.date()), "2025-02-01")

    def test_unrated_not_in_grade_a_denominator(self):
        brooklyn = self.clean[self.clean.borough.eq("Brooklyn")]
        row = cuisine_summary(brooklyn).set_index("cuisine").loc["Chinese"]
        self.assertEqual((row.restaurants, row.rated, row.grade_a_pct), (2, 1, 1.0))
        unknown = cuisine_summary(brooklyn).set_index("cuisine").loc["Unknown"]
        self.assertTrue(pd.isna(unknown.grade_a_pct))

    def test_invalid_dates_and_same_day_conflicts(self):
        by_id = self.clean.set_index("CAMIS")
        for camis in ["2", "4", "7"]:
            self.assertTrue(pd.isna(by_id.loc[camis, "grade"]))
        self.assertEqual(by_id.loc["6", "grade"], "C")
        self.assertEqual(self.audit["latest_date_grade_conflicts"], 1)

    def test_empty_and_no_rated_states(self):
        empty = self.clean.iloc[:0]
        self.assertEqual(len(cuisine_summary(empty)), 0)
        self.assertTrue(scatter_figure(cuisine_summary(empty), None).layout.annotations)
        self.assertTrue(bar_figure(cuisine_summary(empty), None)[0].layout.annotations)
        self.assertTrue(heatmap_figure(empty)[0].layout.annotations)
        self.assertEqual(create_app(empty, {}).server.test_client().get("/").status_code, 200)


class RealSnapshotTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.frame, cls.metadata = load_data()

    def test_source_completeness_and_reconciliations(self):
        raw = read_raw(DATA / "nyc_inspections.csv.gz")
        self.assertEqual(len(raw), self.metadata["official_row_count"])
        self.assertEqual(self.metadata["restaurants"], len(self.frame))
        self.assertEqual(self.frame.groupby("borough").CAMIS.nunique().sum(), len(self.frame))
        self.assertEqual(cuisine_summary(self.frame).restaurants.sum(), len(self.frame))
        # Independently reconstruct latest-grade membership with Python dictionaries.
        latest = {}
        for camis, _, _, date, grade in raw.itertuples(index=False, name=None):
            if grade in ("A", "B", "C") and "1900" < date[:4] and date[:10] <= self.metadata["download_date"]:
                candidate = (date, grade)
                latest[camis] = max(candidate, latest.get(camis, ("", "")))
        expected = {c: latest[c][1] for c in self.frame.CAMIS if c in latest}
        actual = self.frame.dropna(subset=["grade"]).set_index("CAMIS").grade.to_dict()
        self.assertEqual(expected, actual)

    def test_all_five_boroughs_and_heatmap_denominator(self):
        heat, cuisines = heatmap_figure(self.frame)
        for i, boro in enumerate(BOROUGHS):
            subset = self.frame[self.frame.borough.eq(boro)]
            self.assertGreater(len(subset), 0)
            summary = cuisine_summary(subset)
            self.assertEqual(summary.restaurants.sum(), len(subset))
            for j, cuisine in enumerate(cuisines):
                count = int(subset.cuisine.eq(cuisine).sum())
                self.assertEqual(heat.data[0].customdata[i][j][2], count)
                self.assertAlmostEqual(heat.data[0].z[i][j], count / len(subset))

    def test_selection_reset_and_outside_top_ten(self):
        summary = cuisine_summary(self.frame)
        cuisine = summary.iloc[-1].cuisine
        fig, extra = bar_figure(summary, cuisine)
        self.assertTrue(extra)
        self.assertIn(cuisine, fig.data[0].y)
        click = {"points": [{"x": "Chinese", "y": "Brooklyn"}]}
        self.assertEqual(select_state("heatmap", "All NYC", click, None, ["Chinese"]), ("Brooklyn", "Chinese"))
        self.assertEqual(select_state("reset", "Brooklyn", click, "Chinese", ["Chinese"]), ("All NYC", None))
        self.assertEqual(select_state("borough", "Queens", None, "Chinese", ["Chinese"]), ("Queens", None))

    def test_dash_routes(self):
        client = app.server.test_client()
        for route in ["/", "/_dash-layout", "/_dash-dependencies"]:
            self.assertEqual(client.get(route).status_code, 200)


if __name__ == "__main__":
    unittest.main()
