"""A Taste of NYC — three linked views of unique restaurants."""
from __future__ import annotations

import json
import os
import textwrap
from html import escape
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
from dash import Dash, Input, Output, State, ctx, dcc, html

from prepare_data import BOROUGHS, SOURCE_URL

ROOT = Path(__file__).resolve().parent
ABOVE = "#237d75"
BELOW = "#bc641f"
BAR_BACKGROUND = "#aebfc6"
SELECTED = "#355e6a"
MISSING_CUISINE = "Unknown"
HEAT_COLORS = [[0, "#faf5ff"], [0.25, "#d7b5f1"], [0.5, "#9950c9"], [0.75, "#63169b"], [1, "#29004f"]]
INK = "#172033"
CONFIG = {"displayModeBar": False, "responsive": True, "scrollZoom": False}


def load_data():
    path = ROOT / "data/restaurants.csv"
    if not path.exists():
        raise SystemExit("Missing data/restaurants.csv. Run: python prepare_data.py --download")
    frame = pd.read_csv(path, dtype={"CAMIS": "string"})
    if frame.CAMIS.isna().any() or not frame.CAMIS.is_unique:
        raise ValueError("Cleaned data must contain exactly one nonmissing CAMIS per restaurant.")
    metadata = json.loads((ROOT / "data/data_quality.json").read_text())
    return frame, metadata


def cuisine_summary(frame: pd.DataFrame) -> pd.DataFrame:
    """Recompute numerator and denominator at the selected borough's grain."""
    data = frame.assign(rated=frame.grade.isin(["A", "B", "C"]), a=frame.grade.eq("A"))
    summary = data.groupby("cuisine", as_index=False).agg(
        restaurants=("CAMIS", "nunique"), rated=("rated", "sum"), grade_a=("a", "sum"))
    summary["grade_a_pct"] = summary.grade_a / summary.rated.replace(0, float("nan"))
    return summary.sort_values(["restaurants", "cuisine"], ascending=[False, True]).reset_index(drop=True)


def base_figure():
    figure = go.Figure()
    figure.update_layout(template="plotly_white", font={"family": "Arial, sans-serif", "size": 14, "color": INK},
                         paper_bgcolor="white", plot_bgcolor="white", showlegend=False,
                         margin={"l": 60, "r": 25, "t": 20, "b": 55},
                         hoverlabel={"bgcolor": "white", "font_size": 15}, dragmode=False)
    figure.update_xaxes(gridcolor="#f0f1f2", zeroline=False, fixedrange=True)
    figure.update_yaxes(gridcolor="#f0f1f2", zeroline=False, fixedrange=True)
    figure.update_xaxes(title_font={"size": 15}, tickfont={"size": 13}, showline=True, linecolor="#cbd2d7")
    figure.update_yaxes(title_font={"size": 15}, tickfont={"size": 13})
    return figure


def empty_figure(message):
    fig = base_figure()
    fig.add_annotation(text=message, x=0.5, y=0.5, xref="paper", yref="paper", showarrow=False)
    return fig


def scatter_figure(summary, selected, scope="All NYC", min_graded=1):
    # The benchmark is a pooled restaurant-level rate, not a mean of cuisine rates.
    total_rated = int(summary.rated.sum())
    benchmark = float(summary.grade_a.sum() / total_rated) if total_rated else None
    plotted = summary[(summary.rated >= min_graded) & summary.cuisine.ne(MISSING_CUISINE)]
    if plotted.empty:
        return empty_figure("No recorded cuisines meet the graded-sample filter" if min_graded > 1 else "No recorded cuisines with A/B/C grades in this selection")
    fig = base_figure()
    groups = [(plotted[plotted.cuisine.ne(selected)], False), (plotted[plotted.cuisine.eq(selected)], True)]
    for rows, active in groups:
        if rows.empty:
            continue
        colors = [ABOVE if value >= benchmark else BELOW for value in rows.grade_a_pct]
        symbols = [("triangle-up" if value >= benchmark else "square") + ("-open" if n < 10 else "")
                   for value, n in zip(rows.grade_a_pct, rows.rated)]
        relation = ["At or above overall" if value >= benchmark else "Below overall" for value in rows.grade_a_pct]
        custom = [[c, int(n), int(r), int(a), rel, scope] for c, n, r, a, rel in
                  zip(rows.cuisine, rows.restaurants, rows.rated, rows.grade_a, relation)]
        fig.add_trace(go.Scatter(
            x=rows.restaurants.tolist(), y=rows.grade_a_pct.tolist(),
            mode="markers+text" if active else "markers",
            text=[escape(c) for c in rows.cuisine] if active else None,
            textposition="bottom center", textfont={"color": INK, "size": 15}, cliponaxis=False,
            customdata=custom,
            marker={"size": 14 if active else 9, "color": colors,
                    "opacity": 1 if active else 0.85,
                    "symbol": symbols,
                    "line": {"width": 2.5 if active else 1, "color": "#111111" if active else colors}},
            hovertemplate="<b>%{customdata[0]}</b><br>Borough: %{customdata[5]}<br>Restaurants: %{customdata[1]:,}<br>Rated (A/B/C): %{customdata[2]:,}<br>Grade A restaurants: %{customdata[3]:,}<br>Grade A: %{y:.1%}<br>%{customdata[4]}<extra></extra>"))
        if active and int(rows.iloc[0].rated) < 10:
            # Preserve the colored hollow small-sample mark and add a matching black outline.
            fig.add_trace(go.Scatter(x=rows.restaurants.tolist(), y=rows.grade_a_pct.tolist(),
                                    mode="markers", customdata=custom,
                                    hovertemplate="<b>%{customdata[0]}</b><br>Borough: %{customdata[5]}<br>Restaurants: %{customdata[1]:,}<br>Rated (A/B/C): %{customdata[2]:,}<br>Grade A restaurants: %{customdata[3]:,}<br>Grade A: %{y:.1%}<extra></extra>", marker={"size": 17,
                                    "symbol": symbols, "color": "#111111", "line": {"width": 1.5}}))
    fig.add_hline(y=benchmark, line={"color": "#45515c", "width": 1.8, "dash": "dash"}, layer="below")
    # Keep the benchmark label outside the data region so it cannot cover a point.
    fig.add_annotation(x=1, xref="paper", y=1.02, yref="paper", text=f"{escape(scope)} overall Grade A · {benchmark:.1%}",
                       showarrow=False, xanchor="right", yanchor="bottom",
                       font={"size": 14, "color": "#33414c"})
    fig.add_annotation(x=1.015, xref="paper", y=benchmark, yref="y",
                       text=f"<b>{benchmark:.1%}</b>", showarrow=False, xanchor="left", yanchor="middle",
                       font={"size": 13, "color": "#33414c"}, bgcolor="white", borderpad=2)
    fig.update_xaxes(title="Restaurant count", rangemode="tozero", tickformat=",d", type="linear")
    fig.update_yaxes(title="Grade A percentage", range=[-0.04, 1.07], tickformat=".0%", dtick=0.2)
    fig.update_layout(margin={"l": 76, "r": 65, "t": 36, "b": 62})
    return fig


def bar_figure(summary, selected, scope="All NYC"):
    total = int(summary.restaurants.sum())  # Includes unrecorded cuisines.
    summary = summary[summary.cuisine.ne(MISSING_CUISINE)].copy()
    summary["rank"] = range(1, len(summary) + 1)
    if summary.empty:
        return empty_figure("No restaurants in this selection"), False
    top = summary.head(10)
    extra = bool(selected and selected not in top.cuisine.values and selected in summary.cuisine.values)
    if extra:
        top = pd.concat([top, summary[summary.cuisine.eq(selected)]])
    fig = base_figure()
    fig.add_trace(go.Bar(
        x=top.restaurants.tolist(), y=top.cuisine.tolist(), orientation="h",
        marker_color=[SELECTED if c == selected else BAR_BACKGROUND for c in top.cuisine],
        customdata=[[c, int(n), float(n / total), scope, int(rank)] for c, n, rank in zip(top.cuisine, top.restaurants, top["rank"])],
        text=[f"{n:,}" for n in top.restaurants],
        textposition="outside", textfont={"size": 14}, cliponaxis=False,
        hovertemplate="<b>%{customdata[0]}</b><br>Borough: %{customdata[3]}<br>Restaurants: %{x:,}<br>Share of all restaurants: %{customdata[2]:.1%}<br>Rank: %{customdata[4]}<extra></extra>"))
    fig.update_yaxes(title=None, autorange="reversed", showgrid=False, automargin=True,
                     tickvals=top.cuisine.tolist(),
                     ticktext=[(f"<b>{escape(c)}</b><br>Selected cuisine · Rank {rank}" if extra else f"<b>{escape(c)}</b>") if c == selected else escape(c) for c, rank in zip(top.cuisine, top["rank"])], tickfont={"size": 14})
    fig.update_xaxes(title="Restaurant count", range=[0, float(top.restaurants.max()) * 1.22], tickformat=",d")
    fig.update_layout(margin={"l": 185, "r": 38, "t": 8, "b": 52}, bargap=0.33)
    return fig, extra


def heat_text_color(fraction):
    """Choose the more legible text color against the actual interpolated cell fill."""
    fraction = max(0, min(1, fraction))
    for (lo, a), (hi, b) in zip(HEAT_COLORS, HEAT_COLORS[1:]):
        if fraction <= hi:
            t = (fraction - lo) / (hi - lo)
            rgb = [(int(a[k:k+2], 16) * (1-t) + int(b[k:k+2], 16) * t) / 255 for k in (1, 3, 5)]
            linear = [v / 12.92 if v <= 0.04045 else ((v+0.055)/1.055)**2.4 for v in rgb]
            luminance = sum(v*w for v, w in zip(linear, (0.2126, 0.7152, 0.0722)))
            return "#111111" if luminance > 0.179 else "#ffffff"
    return "#ffffff"


def heatmap_figure(frame, borough="All NYC", selected=None):
    if frame.empty:
        return empty_figure("No restaurant data available"), []
    summary = cuisine_summary(frame)
    recorded = summary[summary.cuisine.ne(MISSING_CUISINE)]
    cuisines = recorded.head(10).cuisine.tolist()
    if selected in recorded.cuisine.values and selected not in cuisines:
        cuisines.append(selected)
    if not cuisines:
        return empty_figure("No recorded cuisines available"), []
    counts = pd.crosstab(frame.borough, frame.cuisine).reindex(index=BOROUGHS, columns=cuisines, fill_value=0)
    totals = frame.groupby("borough").CAMIS.nunique().reindex(BOROUGHS, fill_value=0)
    shares = counts.div(totals.replace(0, float("nan")), axis=0)
    detail = [[[b, c, int(counts.loc[b, c]), int(totals[b])] for c in cuisines] for b in BOROUGHS]
    z = [[None if pd.isna(v) else float(v) for v in row] for row in shares.values]
    all_counts = pd.crosstab(frame.borough, frame.cuisine).reindex(index=BOROUGHS, columns=recorded.cuisine, fill_value=0)
    maximum = max(0.01, float(all_counts.div(totals.replace(0, float("nan")), axis=0).max().max()))
    fig = base_figure()
    fig.add_trace(go.Heatmap(
        x=cuisines, y=BOROUGHS, z=z, customdata=detail, zmin=0,
        zmax=maximum,
        colorscale=HEAT_COLORS,
        xgap=2, ygap=2, hoverongaps=False,
        colorbar={"title": {"text": "Share"}, "tickformat": ".0%", "thickness": 13, "len": 0.94},
        hovertemplate="<b>%{customdata[0]} · %{customdata[1]}</b><br>Restaurants: %{customdata[2]:,}<br>Share of borough: %{z:.1%}<br>All borough restaurants: %{customdata[3]:,}<extra></extra>"))
    for i, boro in enumerate(BOROUGHS):
        for j, cuisine in enumerate(cuisines):
            value = z[i][j]
            fig.add_annotation(x=cuisine, y=boro, text=f"{value:.1%}" if value is not None else "—",
                               showarrow=False, captureevents=False,
                               font={"size": 13, "color": heat_text_color(value / maximum) if value is not None else INK})
    if selected in cuisines:
        x = cuisines.index(selected)
        # Every borough in the selected cuisine gets a thin outline.
        for y, boro in enumerate(BOROUGHS):
            active = boro == borough
            for inset, color, width in [(0.49, "#111111", 3 if active else 1),
                                        (0.44, "white", 1.5 if active else 0.6)]:
                fig.add_shape(type="rect", x0=x-inset, x1=x+inset, y0=y-inset, y1=y+inset,
                              xref="x", yref="y", line={"color": color, "width": width}, fillcolor="rgba(0,0,0,0)")
    # Full category names stay in hover; line wrapping avoids rotated, clipped ticks.
    labels = {"Coffee/Tea": "Coffee /<br>Tea", "Juice, Smoothies, Fruit Salads": "Juice /<br>Smoothies", "Latin American": "Latin<br>American", "Bakery Products/Desserts": "Bakery /<br>Desserts"}
    ticks = [labels.get(c, "<br>".join(textwrap.wrap(c, 11))) for c in cuisines]
    ticks = [f"<b>{t}</b>" if c == selected else t for c, t in zip(cuisines, ticks)]
    fig.update_xaxes(title="Cuisine · NYC top 10" + (" + selected" if len(cuisines) > 10 else ""), tickvals=cuisines, ticktext=ticks, tickangle=-40, showgrid=False, showline=False,
                     tickfont={"size": 13})
    fig.update_yaxes(title=None, autorange="reversed", showgrid=False, tickvals=BOROUGHS,
                     ticktext=[f"<b>{b}</b>" if b == borough else b for b in BOROUGHS])
    fig.update_layout(margin={"l": 116, "r": 22, "t": 10, "b": 104})
    return fig, cuisines


def select_state(trigger, borough, click_data, selected, heat_cuisines):
    """A small state reducer; no shared mutable selection between browser sessions."""
    if trigger == "reset":
        return "All NYC", None
    if trigger == "heatmap" and click_data and click_data.get("points"):
        point = click_data["points"][0]
        if point.get("y") in BOROUGHS and point.get("x") in heat_cuisines:
            return point["y"], point["x"]
    if trigger in ("bar", "scatter") and click_data and click_data.get("points"):
        point = click_data["points"][0]
        custom = point.get("customdata")
        cuisine = custom[0] if isinstance(custom, (list, tuple)) and custom else point.get("y") if trigger == "bar" else None
        if cuisine in heat_cuisines:
            selected = cuisine
    if trigger == "borough":
        selected = None
    return borough if borough in ["All NYC", *BOROUGHS] else "All NYC", selected


def create_app(frame=None, metadata=None):
    if frame is None:
        frame, metadata = load_data()
    metadata = metadata or {}
    heatmap, heat_cuisines = heatmap_figure(frame)
    all_cuisines = set(frame.loc[frame.cuisine.ne(MISSING_CUISINE), "cuisine"])
    app = Dash(__name__, title="A Taste of NYC", assets_folder=str(ROOT / "assets"))
    app.layout = html.Main([
        html.Header([
            html.Div([html.H1("A Taste of NYC"),
                      html.P("Cuisine and restaurant inspection grades across New York City.", className="intro")]),
            html.Div([html.Span("Data snapshot"), html.Strong(metadata.get("download_date", "Unknown"))], className="snapshot"),
        ]),
        html.Div([
            html.Div([html.Label("Borough", htmlFor="borough"),
                      dcc.Dropdown(id="borough", options=["All NYC", *BOROUGHS], value="All NYC", clearable=False, searchable=False)], className="filter"),
            html.Button("Reset", id="reset", n_clicks=0),
            html.Div([html.Span("Selection", className="selection-label"), html.Strong(id="selection")], className="selection", **{"aria-live": "polite"}),
            html.P("Click a point, bar, or heatmap cell to link the views.", className="hint"),
        ], className="controls"),
        dcc.Store(id="selected-cuisine", data=None),
        html.Div(id="metrics", className="metrics"),
        html.Div([
            html.Section([
                html.Div([html.Span("01", className="rq"), html.H2("Cuisine size & inspection grades")], className="chart-title"),
                html.P(id="scatter-scope", className="chart-subtitle"),
                html.Div([
                    html.Span([html.Img(src="/assets/legend-triangle.svg", className="key-mark", alt=""), "At or above overall"]),
                    html.Span([html.Img(src="/assets/legend-square.svg", className="key-mark", alt=""), "Below overall"]),
                    html.Span([html.I(className="key-line"), "Dashed line: overall Grade A %"], className="key-reference"),
                    html.Span([
                        html.Span([html.Img(src="/assets/legend-triangle-open.svg", className="key-mark", alt=""),
                                   html.Img(src="/assets/legend-square-open.svg", className="key-mark", alt="")], className="key-symbols"),
                        html.Span("Hollow symbols: fewer than 10 A/B/C-graded restaurants per cuisine"),
                    ], className="key-note"),
                ], className="plot-key"),
                html.Div([
                    dcc.Checklist(id="sample-filter", options=[{"label": "At least 10 graded restaurants", "value": "ten"}], value=[]),
                    html.Span(id="sample-status", **{"aria-live": "polite"}),
                ], className="sample-controls"),
                dcc.Graph(id="scatter", config=CONFIG, responsive=True, style={"height": "450px"}, className="scatter-plot"),
                html.P("Each point is a cuisine; the dashed line is the overall rate among graded restaurants.", className="figure-note"),
            ], className="panel scatter-panel"),
            html.Div([
                html.Section([
                    html.Div([html.Span("02", className="rq"), html.H2(id="bar-title")], className="chart-title"),
                    html.P(id="bar-scope", className="chart-subtitle"),
                    dcc.Graph(id="bar", config=CONFIG, responsive=True, style={"height": "330px"}, className="bar-plot"),
                ], className="panel"),
                html.Section([
                    html.Div([html.Span("03", className="rq"), html.H2("Cuisine share by borough", id="heatmap-title")], className="chart-title"),
                    html.P("NYC top 10 · Share within each borough · All five boroughs", className="chart-subtitle"),
                    dcc.Graph(id="heatmap", figure=heatmap, config=CONFIG, responsive=True, style={"height": "290px"}, className="heatmap-plot"),
                ], className="panel"),
            ], className="right-column"),
        ], className="chart-grid"),
        html.P(id="missing-note", className="missing-note"),
        html.Details([
            html.Summary("Data notes"),
            html.P("Counts represent unique restaurants. Grade A percentages use each restaurant’s latest available A/B/C graded inspection."),
            html.P("Overall Grade A = all Grade A restaurants / all A/B/C-rated restaurants in the selected scope; it is not an average of cuisine percentages. The reference and both color groups update with the borough."),
            html.P("Cuisine not recorded is excluded from the cuisine comparisons but included in total counts and heatmap denominators. Heatmap columns are the NYC top 10 recorded cuisines, plus the selected cuisine if needed; all five boroughs and the citywide color scale remain fixed."),
            html.P(id="scatter-note"),
            html.P("Small samples may have extreme percentages. Above/below overall is descriptive, not a significance test. The X axis remains linear. A black outline and label identify the selected scatter point without changing its comparison color."),
            html.P("Source includes active establishments and not-yet-inspected applicants. It is not an all-time census."),
        ], className="data-notes"),
        html.Footer([html.A("NYC DOHMH Restaurant Inspection Results", href=SOURCE_URL, target="_blank", rel="noreferrer"),
                     f" · Downloaded {metadata.get('download_date', 'unknown')}"]),
    ], className="page")

    @app.callback(
        Output("borough", "value"), Output("selected-cuisine", "data"),
        Output("heatmap", "clickData"), Output("scatter", "figure"), Output("bar", "figure"),
        Output("selection", "children"), Output("metrics", "children"),
        Output("scatter-scope", "children"), Output("bar-scope", "children"),
        Output("bar-title", "children"), Output("scatter-note", "children"),
        Output("heatmap", "figure"), Output("missing-note", "children"),
        Output("bar", "clickData"), Output("scatter", "clickData"),
        Output("sample-filter", "value"), Output("sample-status", "children"), Output("heatmap-title", "children"),
        Input("borough", "value"), Input("heatmap", "clickData"), Input("reset", "n_clicks"),
        Input("bar", "clickData"), Input("scatter", "clickData"), Input("sample-filter", "value"),
        State("selected-cuisine", "data"),
    )
    def update(borough, click_data, reset_clicks, bar_click, scatter_click, sample_filter, selected):
        trigger = ctx.triggered_id
        click = {"heatmap": click_data, "bar": bar_click, "scatter": scatter_click}.get(trigger)
        borough, selected = select_state(trigger, borough, click, selected, all_cuisines)
        sample_filter = [] if trigger == "reset" else (sample_filter or [])
        minimum = 10 if "ten" in sample_filter else 1
        subset = frame if borough == "All NYC" else frame[frame.borough.eq(borough)]
        summary = cuisine_summary(subset)
        bar, extra = bar_figure(summary, selected, borough)
        rated = int(subset.grade.isin(["A", "B", "C"]).sum())
        grade_a = int(subset.grade.eq("A").sum())
        metrics = f"{len(subset):,} restaurants · {rated:,} with A/B/C grades · " + (f"{grade_a / rated:.1%} Grade A overall" if rated else "Grade A: no data")
        unknown = int(subset.cuisine.eq(MISSING_CUISINE).sum())
        missing_note = f"Cuisine not recorded: {unknown:,} in {borough}. Included in totals and share denominators; excluded from cuisine comparisons."
        omitted = int((summary.rated.eq(0) & summary.cuisine.ne(MISSING_CUISINE)).sum())
        note = f"{omitted} recorded cuisine(s) have no valid grade and are not plotted in scatter. Counts still include them. The optional minimum-sample filter affects only scatter visibility, not totals or the overall benchmark."
        hidden = int(((summary.rated > 0) & (summary.rated < minimum) & summary.cuisine.ne(MISSING_CUISINE)).sum())
        sample_status = f"{hidden} cuisines hidden by sample filter"
        if omitted:
            sample_status += f" · {omitted} with no grade not plotted"
        if selected:
            row = summary[summary.cuisine.eq(selected)]
            if row.empty:
                note = f"{selected}: 0 restaurants; Grade A: no data. " + note
                sample_status += f" · {selected}: no restaurants in this borough"
            elif int(row.iloc[0].rated) == 0:
                note = f"{selected}: Grade A unavailable (0 rated restaurants). " + note
                sample_status += f" · {selected}: no valid grade"
            elif int(row.iloc[0].rated) < minimum:
                sample_status += f" · {selected} is hidden ({int(row.iloc[0].rated)} graded); turn off the filter to see it"
        return (borough, selected, None, scatter_figure(summary, selected, borough, minimum), bar,
                f"{borough} · {selected or 'All cuisines'}", metrics,
                f"{borough} · Recorded cuisines with A/B/C grades",
                f"{borough} · Top 10 by unique restaurant count",
                "Most common cuisines" + (" · + selected" if extra else ""), note,
                heatmap_figure(frame, borough, selected)[0], missing_note,
                None, None, sample_filter, sample_status,
                "Cuisine share by borough" + (" · + selected" if selected and selected not in heat_cuisines else ""))

    return app


app = create_app()
server = app.server

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=int(os.environ.get("PORT", "8050")), debug=False)
