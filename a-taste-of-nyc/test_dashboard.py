"""Run with python -m unittest -v. No extra test packages required."""
import unittest

import pandas as pd
from borough_map import BoroughMap

from prepare_data import BOROUGHS, FIELDS, clean_restaurants, read_raw, DATA
from app import (app, bar_figure, create_app, cuisine_summary, heatmap_figure,
                 load_data, scatter_figure, select_state, ABOVE, BELOW, SELECTED, SMALL_SAMPLE,
                 HEAT_COLORS, heat_text_color, metrics_view)


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
        self.assertEqual(select_state("borough", "Queens", None, "Chinese", ["Chinese"]), ("Queens", "Chinese"))

    def test_missing_cuisine_really_missing_in_all_source_records(self):
        raw = read_raw(DATA / "nyc_inspections.csv.gz")
        unknown = self.frame[self.frame.cuisine.eq("Unknown")]
        source = raw[raw.CAMIS.isin(unknown.CAMIS)]
        self.assertEqual(len(unknown), 3922)
        self.assertEqual(int(unknown.borough.eq("Brooklyn").sum()), 992)
        self.assertFalse(source["CUISINE DESCRIPTION"].str.strip().ne("").any())
        self.assertFalse(unknown.grade.isin(["A", "B", "C"]).any())
        self.assertNotIn("Unknown", heatmap_figure(self.frame)[1])
        self.assertNotIn("Unknown", bar_figure(cuisine_summary(self.frame), None)[0].data[0].y)

    def test_pooled_benchmark_and_selection_preserves_color(self):
        for boro in ["All NYC", *BOROUGHS]:
            frame = self.frame if boro == "All NYC" else self.frame[self.frame.borough.eq(boro)]
            expected = frame.grade.eq("A").sum() / frame.grade.isin(["A", "B", "C"]).sum()
            summary = cuisine_summary(frame)
            fig = scatter_figure(summary, "Chinese", boro)
            self.assertAlmostEqual(fig.layout.shapes[0].y0, expected)
            for trace in fig.data:
                if trace.customdata is None:
                    continue
                for rate, color, symbol, detail in zip(trace.y, trace.marker.color, trace.marker.symbol, trace.customdata):
                    self.assertEqual(color, SMALL_SAMPLE if detail[2] < 10 else ABOVE if rate >= expected else BELOW)
                    expected_symbol = "square-open" if detail[2] < 10 else "triangle-up" if rate >= expected else "circle"
                    self.assertEqual(symbol, expected_symbol)
            selected = [t for t in fig.data if t.text and "Chinese" in t.text][0]
            self.assertEqual(selected.marker.line.color, SELECTED)
        # A deliberately skewed fixture distinguishes a pooled rate from average rates,
        # and confirms graded missing-cuisine records stay in the overall denominator.
        summary = pd.DataFrame({"cuisine": ["One", "Many", "Unknown"], "restaurants": [1,99,100],
                                "rated": [1,99,100], "grade_a": [1,0,100], "grade_a_pct": [1.,0.,1.]})
        fig = scatter_figure(summary, None)
        self.assertEqual(fig.layout.shapes[0].y0, 101/200)
        self.assertEqual(len(fig.data[0].x), 2)
        self.assertEqual(fig.data[0].marker.symbol[0], "square-open")
        # The three categories use exactly three shapes; small-sample status wins.
        summary = pd.DataFrame({"cuisine": ["High", "Low", "Small high", "Small low"],
                                "restaurants": [10, 10, 9, 9], "rated": [10, 10, 9, 9],
                                "grade_a": [10, 0, 9, 0], "grade_a_pct": [1., 0., 1., 0.]})
        fig = scatter_figure(summary, None)
        self.assertEqual(list(fig.data[0].marker.symbol), ["triangle-up", "circle", "square-open", "square-open"])

    def test_heatmap_labels_selection_and_fixed_scale(self):
        default, cuisines = heatmap_figure(self.frame)
        selected, _ = heatmap_figure(self.frame, "Brooklyn", "Chinese")
        self.assertEqual(default.data[0].zmax, selected.data[0].zmax)
        self.assertEqual(len(default.layout.annotations), 50)
        self.assertEqual(len(selected.layout.shapes), 10)
        self.assertEqual(len(default.layout.shapes), 0)
        self.assertIn("<b>Brooklyn</b>", selected.layout.yaxis.ticktext)
        i, j = BOROUGHS.index("Brooklyn"), cuisines.index("Chinese")
        self.assertEqual(selected.layout.annotations[i*10+j].text, "8.1%")

    def test_scatter_zoom_preserves_data_and_low_rate_selection(self):
        summary = cuisine_summary(self.frame)
        expected = summary[(summary.rated > 0) & summary.cuisine.ne("Unknown")].set_index("cuisine")
        zoom = scatter_figure(summary, None)
        actual = {row[0]: (count, rate) for trace in zoom.data
                  for count, rate, row in zip(trace.x, trace.y, trace.customdata)}
        self.assertEqual(set(actual), set(expected.index))
        for cuisine, (count, rate) in actual.items():
            self.assertEqual(count, expected.loc[cuisine, "restaurants"])
            self.assertAlmostEqual(rate, expected.loc[cuisine, "grade_a_pct"])
            self.assertLessEqual(10 ** zoom.layout.xaxis.range[0], count)
            self.assertGreaterEqual(10 ** zoom.layout.xaxis.range[1], count)
        self.assertLess(zoom.layout.yaxis.range[1] - zoom.layout.yaxis.range[0], 0.3)
        # Low-rate cuisines remain in the data, and selecting one reveals its true rate.
        low_cuisine = expected.grade_a_pct.idxmin()
        selected = scatter_figure(summary, low_cuisine)
        rate = float(expected.loc[low_cuisine, "grade_a_pct"])
        self.assertLessEqual(selected.layout.yaxis.range[0], rate)
        self.assertGreaterEqual(selected.layout.yaxis.range[1], rate)
        self.assertLessEqual(selected.layout.yaxis.range[0], selected.layout.shapes[0].y0)
        full_range = zoom.layout.meta["scatter_ranges"]["full"]["range"]
        self.assertTrue(all(full_range[0] <= rate <= full_range[1] for _, rate in actual.values()))

    def test_heatmap_grayscale_order_and_cell_text_contrast(self):
        def luminance(channels):
            linear = [v / 12.92 if v <= 0.04045 else ((v + .055) / 1.055) ** 2.4
                      for v in channels]
            return sum(v * weight for v, weight in zip(linear, (.2126, .7152, .0722)))
        def rgb(color):
            return [int(color[k:k+2], 16) / 255 for k in (1, 3, 5)]
        # Quantitative order must remain visible after color is removed.
        levels = [luminance(rgb(color)) for _, color in HEAT_COLORS]
        self.assertTrue(all(a > b for a, b in zip(levels, levels[1:])))
        # Audit the interpolated ramp too, including shades between stored stops.
        for i in range(257):
            fraction = i / 256
            lo, hi = next((a, b) for a, b in zip(HEAT_COLORS, HEAT_COLORS[1:]) if fraction <= b[0])
            weight = (fraction - lo[0]) / (hi[0] - lo[0])
            background = luminance([a * (1-weight) + b * weight for a, b in zip(rgb(lo[1]), rgb(hi[1]))])
            foreground = luminance(rgb(heat_text_color(fraction)))
            contrast = (max(background, foreground) + .05) / (min(background, foreground) + .05)
            self.assertGreaterEqual(contrast, 4.5)

    def test_dash_routes(self):
        client = app.server.test_client()
        for route in ["/", "/_dash-layout", "/_dash-dependencies"]:
            self.assertEqual(client.get(route).status_code, 200)

    def test_map_matches_heatmap_and_preserves_denominators(self):
        model = BoroughMap(self.frame, BOROUGHS, HEAT_COLORS)
        self.assertEqual(set(model.geometry), set(BOROUGHS))
        for cuisine in ("Chinese", "Frozen Desserts", "American"):
            heat, cuisines = heatmap_figure(self.frame, "Brooklyn", cuisine)
            figure, actual = model.figure("Brooklyn", cuisine)
            self.assertEqual(actual, cuisine)
            self.assertEqual(figure.data[-1].marker.cmax, heat.data[0].zmax)
            for i, row in enumerate(figure.layout.meta["boroughs"]):
                j = cuisines.index(cuisine)
                self.assertEqual(row["borough"], BOROUGHS[i])
                self.assertAlmostEqual(row["share"], heat.data[0].z[i][j])
                self.assertEqual(row["restaurants"], heat.data[0].customdata[i][j][2])
                self.assertEqual(row["total"], heat.data[0].customdata[i][j][3])
                # Each polygon trace keeps a stable click index across cuisine changes.
                self.assertEqual(figure.data[i].name, BOROUGHS[i])
            self.assertEqual(figure.data[BOROUGHS.index("Brooklyn")].line.width, 2.5)
        self.assertIsNone(model.focus())
        neutral, cuisine = model.figure()
        self.assertIsNone(cuisine)
        self.assertEqual(len(neutral.data), 5)
        self.assertTrue(all(row["share"] is None for row in neutral.layout.meta["boroughs"]))
        self.assertIsNone(model.focus(None, ()))
        empty, cuisine = model.figure("All NYC", None, ())
        self.assertIsNone(cuisine)
        self.assertTrue(all(row["share"] is None for row in empty.layout.meta["boroughs"]))
        self.assertEqual(select_state("borough-map", "All NYC", {"points":[{"curveNumber":1}]}, "Chinese", []),
                         (BOROUGHS[1], "Chinese"))
        self.assertEqual(select_state("borough-map", "All NYC", {"points":[{"curveNumber":5}]}, "Chinese", []),
                         ("All NYC", "Chinese"))

    def test_three_way_callback_filter_and_reset(self):
        client = app.server.test_client()
        key, callback = next(iter(app.callback_map.items()))

        def update(trigger, borough="All NYC", cuisine=None, click=None, sample=1, focus=None, count="all", view="heatmap"):
            values = [borough, click if trigger == "heatmap" else None, 1,
                      click if trigger == "bar" else None, click if trigger == "scatter" else None, sample, focus, count, click if trigger == "borough-map" else None]
            inputs = [dict(item, value=value) for item, value in zip(callback["inputs"], values)]
            prop = "value" if trigger in ("borough", "sample-filter", "cuisine-focus", "count-filter") else "n_clicks" if trigger == "reset" else "clickData"
            response = client.post("/_dash-update-component", json={
                "output": key, "outputs": [{"id": o.component_id, "property": o.component_property} for o in callback["output"]],
                "inputs": inputs, "state": [{"id": "selected-cuisine", "property": "data", "value": cuisine},
                                            {"id": "borough-view", "property": "value", "value": view}],
                "changedPropIds": [f"{trigger}.{prop}"]})
            self.assertEqual(response.status_code, 200, response.data)
            return response.get_json()["response"]

        for trigger in ("bar", "scatter"):
            result = update(trigger, click={"points": [{"customdata": ["Chinese"]}]})
            self.assertEqual(result["selection"]["children"], "All NYC · Chinese")
            self.assertGreater(sum(len(t["x"]) for t in result["scatter-source"]["data"]["data"]), 10)
            self.assertEqual(len(result["heatmap"]["figure"]["layout"]["shapes"]), 10)
            self.assertIsNone(result[trigger]["clickData"])
        result = update("heatmap", click={"points": [{"x": "Chinese", "y": "Brooklyn"}]})
        self.assertEqual(result["borough"]["value"], "Brooklyn")
        self.assertIn("8,021", result["metrics"]["children"][0]["props"]["children"])
        facts = result["metrics"]["children"][1]["props"]["children"]
        def text_content(value):
            if isinstance(value, dict):
                return text_content(value.get("props", {}).get("children", ""))
            if isinstance(value, list):
                return " ".join(text_content(v) for v in value)
            return str(value)
        for expected in ["Chinese", "647", "86.7%", "592 graded", "8.1%"]:
            self.assertIn(expected, text_content(facts))
        mapped = update("borough-map", cuisine="Chinese", click={"points":[{"curveNumber":BOROUGHS.index("Brooklyn")}]})
        self.assertEqual(mapped["selection"]["children"], "Brooklyn · Chinese")
        self.assertIsNone(mapped["borough-map"]["clickData"])
        self.assertEqual(mapped["borough-map"]["figure"]["layout"]["meta"]["cuisine"], "Chinese")
        constrained = update("borough-map", cuisine="Chinese", count="100-499",
                             click={"points":[{"curveNumber":BOROUGHS.index("Brooklyn")}]})
        self.assertEqual(constrained["count-filter"]["value"], "all")
        refocused = update("count-filter", cuisine="American", count="1-9", view="map")
        focus = refocused["selected-cuisine"]["data"]
        self.assertIsNone(focus)
        self.assertIsNone(refocused["cuisine-focus"]["value"])
        self.assertEqual(refocused["borough-map"]["figure"]["layout"]["meta"]["cuisine"],focus)
        reset_map = update("reset", cuisine="Chinese", view="map")
        self.assertIsNone(reset_map["selected-cuisine"]["data"])
        unchanged = update("sample-filter", view="map")
        self.assertIsNone(unchanged["selected-cuisine"]["data"])
        self.assertIsNone(unchanged["cuisine-focus"]["value"])
        self.assertIn("Choose a cuisine", unchanged["map-cuisine"]["children"])
        neutral_click = update("borough-map", view="map", click={"points":[{"curveNumber":1}]})
        self.assertEqual(neutral_click["borough"]["value"], BOROUGHS[1])
        self.assertIsNone(neutral_click["selected-cuisine"]["data"])
        summary = cuisine_summary(self.frame)
        rare = summary[(summary.rated > 0) & (summary.rated < 10)].iloc[-1].cuisine
        selected = update("scatter", click={"points": [{"customdata": [rare]}]})
        self.assertIn(rare, selected["bar"]["figure"]["data"][0]["y"])
        self.assertTrue(any("Rank" in text for text in selected["bar"]["figure"]["data"][0]["text"]))
        self.assertEqual(len(selected["heatmap"]["figure"]["data"][0]["x"]), 11)
        filtered = update("sample-filter", cuisine=rare, sample=10)
        self.assertIn("is hidden", filtered["sample-status"]["children"])
        self.assertEqual(filtered["selected-cuisine"]["data"], rare)
        self.assertEqual(filtered["metrics"], selected["metrics"])
        for trace in filtered["scatter-source"]["data"]["data"]:
            self.assertTrue(all(row[2] >= 10 for row in trace["customdata"]))
        self.assertEqual(selected["scatter-source"]["data"]["layout"]["shapes"], filtered["scatter-source"]["data"]["layout"]["shapes"])
        self.assertEqual(selected["heatmap"]["figure"]["data"][0]["zmax"], filtered["heatmap"]["figure"]["data"][0]["zmax"])
        reset = update("reset", "Brooklyn", rare, sample=10)
        self.assertEqual(reset["selection"]["children"], "All NYC · All cuisines")
        self.assertEqual(reset["sample-filter"]["value"], 1)
        self.assertIsNone(reset["cuisine-focus"]["value"])
        focused = update("cuisine-focus", focus="Chinese")
        self.assertEqual(focused["cuisine-focus"]["value"], "Chinese")
        self.assertEqual(focused["selection"]["children"], "All NYC · Chinese")
        self.assertEqual(len(focused["heatmap"]["figure"]["layout"]["shapes"]), 10)
        moved = update("borough", "Brooklyn", "Chinese", sample=25, focus="Chinese")
        self.assertEqual(moved["selection"]["children"], "Brooklyn · Chinese")
        self.assertIn({"label": "Chinese", "value": "Chinese"}, moved["cuisine-focus"]["options"])
        cleared = update("cuisine-focus", "Brooklyn", "Chinese", sample=25)
        self.assertEqual(cleared["selection"]["children"], "Brooklyn · All cuisines")
        self.assertEqual(cleared["sample-filter"]["value"], 25)
        for limit in (1, 10, 25, 50, 100):
            filtered = update("sample-filter", sample=limit)
            traces = filtered["scatter-source"]["data"]["data"]
            plotted = {r[0] for t in traces for r in t["customdata"]}
            expected = set(summary.loc[(summary.rated >= limit) & summary.cuisine.ne("Unknown"), "cuisine"])
            self.assertEqual(plotted, expected)
            self.assertEqual(filtered["metrics"]["children"][0], focused["metrics"]["children"][0])
            self.assertEqual(filtered["scatter-source"]["data"]["layout"]["shapes"], focused["scatter-source"]["data"]["layout"]["shapes"])
        absent = next(c for c in summary.cuisine if c != "Unknown" and c not in set(self.frame.loc[self.frame.borough.eq("Staten Island"), "cuisine"]))
        no_data = update("cuisine-focus", "Staten Island", focus=absent)
        self.assertIn("no restaurants in this borough", no_data["sample-status"]["children"])
        # Count bands partition recorded cuisines without changing pooled rates,
        # borough denominators, or the heatmap color scale.
        from app import COUNT_RANGES
        for count, (_, low, high) in list(COUNT_RANGES.items())[1:]:
            filtered = update("count-filter", count=count)
            eligible = summary[summary.cuisine.ne("Unknown") & summary.restaurants.ge(low)]
            if high is not None:
                eligible = eligible[eligible.restaurants.le(high)]
            expected = set(eligible.cuisine)
            self.assertEqual({o["value"] for o in filtered["cuisine-focus"]["options"]}, expected)
            for trace in filtered["scatter-source"]["data"]["data"]:
                for row in trace["customdata"]:
                    self.assertIn(row[0], expected)
            self.assertEqual(filtered["metrics"]["children"][0], focused["metrics"]["children"][0])
            if filtered["scatter-source"]["data"]["data"]:
                self.assertEqual(filtered["scatter-source"]["data"]["layout"]["shapes"], focused["scatter-source"]["data"]["layout"]["shapes"])
            for row in filtered["bar"]["figure"]["data"][0]["customdata"]:
                self.assertIn(row[0], expected)
                self.assertAlmostEqual(row[2], row[1] / len(self.frame))
            heat = filtered["heatmap"]["figure"]["data"][0]
            self.assertTrue(set(heat["x"]).issubset(expected))
            self.assertEqual(heat["zmax"], focused["heatmap"]["figure"]["data"][0]["zmax"])
            for zrow, detailrow in zip(heat["z"], heat["customdata"]):
                for z, detail in zip(zrow, detailrow):
                    self.assertAlmostEqual(z, detail[2] / detail[3])
        cleared = update("count-filter", cuisine="Chinese", count="1-9")
        self.assertIsNone(cleared["selected-cuisine"]["data"])
        empty = update("sample-filter", count="1-9", sample=100)
        self.assertFalse(empty["scatter-source"]["data"]["data"])
        self.assertTrue(empty["scatter-source"]["data"]["layout"]["annotations"])
        reset = update("reset", "Brooklyn", "Chinese", sample=100, count="1-9")
        self.assertEqual(reset["count-filter"]["value"], "all")
        self.assertEqual(reset["sample-filter"]["value"], 1)
        moved = update("heatmap", count="100-499", click={"points": [{"x": "Chinese", "y": "Brooklyn"}]})
        self.assertEqual(moved["count-filter"]["value"], "all")
        self.assertEqual(moved["selection"]["children"], "Brooklyn · Chinese")

    def test_hover_denominators_and_context(self):
        frame = self.frame[self.frame.borough.eq("Brooklyn")]
        summary = cuisine_summary(frame)
        bar, _ = bar_figure(summary, "Chinese", "Brooklyn")
        for cuisine, count, share, scope, rank in bar.data[0].customdata:
            self.assertAlmostEqual(share, count / len(frame))
            self.assertEqual(scope, "Brooklyn")
        scatter = scatter_figure(summary, "Chinese", "Brooklyn")
        for trace in scatter.data:
            for cuisine, count, rated, grade_a, relation, scope in trace.customdata:
                restaurants = frame[frame.cuisine.eq(cuisine)]
                self.assertEqual((count, rated, grade_a, scope),
                                 (len(restaurants), restaurants.grade.isin(["A", "B", "C"]).sum(), restaurants.grade.eq("A").sum(), "Brooklyn"))


if __name__ == "__main__":
    unittest.main()
