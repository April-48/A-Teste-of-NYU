"""A Taste of NYC — three linked views of unique restaurants."""
from __future__ import annotations

import json
import os
import textwrap
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
from dash import Dash, Input, Output, State, ctx, dcc, html

from prepare_data import BOROUGHS, SOURCE_URL

ROOT = Path(__file__).resolve().parent
PURPLE = "#7160a6"
SELECTED = "#b35c16"
INK = "#2b253b"
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
    figure.update_layout(template="plotly_white", font={"family": "Arial, sans-serif", "size": 12, "color": INK},
                         paper_bgcolor="white", plot_bgcolor="white", showlegend=False,
                         margin={"l": 60, "r": 25, "t": 20, "b": 55},
                         hoverlabel={"bgcolor": "white", "font_size": 13}, dragmode=False)
    figure.update_xaxes(gridcolor="#eeeaf3", zeroline=False, fixedrange=True)
    figure.update_yaxes(gridcolor="#eeeaf3", zeroline=False, fixedrange=True)
    return figure


def empty_figure(message):
    fig = base_figure()
    fig.add_annotation(text=message, x=0.5, y=0.5, xref="paper", yref="paper", showarrow=False)
    return fig


def scatter_figure(summary, selected):
    plotted = summary[summary.rated > 0]
    if plotted.empty:
        return empty_figure("No A/B/C graded restaurants in this selection")
    fig = base_figure()
    # Draw the selection last so an overlapping point cannot obscure it.
    groups = [(plotted[plotted.cuisine.ne(selected)], False), (plotted[plotted.cuisine.eq(selected)], True)]
    for rows, active in groups:
        if rows.empty:
            continue
        fig.add_trace(go.Scatter(
            x=rows.restaurants.tolist(), y=rows.grade_a_pct.tolist(),
            mode="markers+text" if active else "markers",
            text=rows.cuisine.tolist() if active else None, textposition="bottom center",
            textfont={"color": SELECTED, "size": 13}, cliponaxis=False,
            customdata=rows[["cuisine", "restaurants", "rated", "grade_a"]].values.tolist(),
            marker={"size": 15 if active else 10, "color": SELECTED if active else PURPLE,
                    "opacity": 1 if active else 0.7,
                    "symbol": ["diamond" if active else ("circle-open" if n < 10 else "circle") for n in rows.rated],
                    "line": {"width": 1.5, "color": SELECTED if active else PURPLE}},
            hovertemplate="<b>%{customdata[0]}</b><br>Restaurants: %{customdata[1]:,}<br>Rated (A/B/C): %{customdata[2]:,}<br>Grade A: %{y:.1%}<extra></extra>"))
    fig.update_xaxes(title="Restaurant count", rangemode="tozero", tickformat=",d")
    fig.update_yaxes(title="Grade A percentage", range=[-0.04, 1.07], tickformat=".0%", dtick=0.2)
    fig.update_layout(margin={"l": 70, "r": 35, "t": 35, "b": 60})
    return fig


def bar_figure(summary, selected):
    if summary.empty:
        return empty_figure("No restaurants in this selection"), False
    top = summary.head(10)
    extra = bool(selected and selected not in top.cuisine.values and selected in summary.cuisine.values)
    if extra:
        top = pd.concat([top, summary[summary.cuisine.eq(selected)]])
    fig = base_figure()
    fig.add_trace(go.Bar(
        x=top.restaurants.tolist(), y=top.cuisine.tolist(), orientation="h",
        marker_color=[SELECTED if c == selected else PURPLE for c in top.cuisine],
        text=[f"{n:,}" + (" ◀" if c == selected else "") for c, n in zip(top.cuisine, top.restaurants)],
        textposition="outside", cliponaxis=False,
        hovertemplate="<b>%{y}</b><br>Restaurants: %{x:,}<extra></extra>"))
    fig.update_yaxes(title="Cuisine", autorange="reversed", showgrid=False, automargin=True)
    fig.update_xaxes(title="Restaurant count", range=[0, float(top.restaurants.max()) * 1.22], tickformat=",d")
    fig.update_layout(margin={"l": 155, "r": 35, "t": 5, "b": 45}, bargap=0.3)
    return fig, extra


def heatmap_figure(frame):
    if frame.empty:
        return empty_figure("No restaurant data available"), []
    cuisines = cuisine_summary(frame).head(10).cuisine.tolist()
    counts = pd.crosstab(frame.borough, frame.cuisine).reindex(index=BOROUGHS, columns=cuisines, fill_value=0)
    totals = frame.groupby("borough").CAMIS.nunique().reindex(BOROUGHS, fill_value=0)
    shares = counts.div(totals.replace(0, float("nan")), axis=0)
    detail = [[[b, c, int(counts.loc[b, c]), int(totals[b])] for c in cuisines] for b in BOROUGHS]
    z = [[None if pd.isna(v) else float(v) for v in row] for row in shares.values]
    fig = base_figure()
    fig.add_trace(go.Heatmap(
        x=cuisines, y=BOROUGHS, z=z, customdata=detail, zmin=0,
        zmax=max(0.01, float(shares.max().max())),
        colorscale=[[0, "#f5f1fb"], [0.25, "#d8cbe9"], [0.6, "#9b7bc1"], [1, "#523179"]],
        xgap=2, ygap=2, hoverongaps=False,
        colorbar={"title": {"text": "Share"}, "tickformat": ".0%", "thickness": 10, "len": 0.94},
        hovertemplate="<b>%{customdata[0]} · %{customdata[1]}</b><br>Restaurants: %{customdata[2]:,}<br>Share of borough: %{z:.1%}<br>All borough restaurants: %{customdata[3]:,}<extra></extra>"))
    # Full category names stay in hover; line wrapping avoids rotated, clipped ticks.
    labels = {"Coffee/Tea": "Coffee /<br>Tea", "Juice, Smoothies, Fruit Salads": "Juice /<br>Smoothies", "Latin American": "Latin<br>American", "Bakery Products/Desserts": "Bakery /<br>Desserts"}
    ticks = [labels.get(c, "<br>".join(textwrap.wrap(c, 11))) for c in cuisines]
    fig.update_xaxes(title="Cuisine · NYC top 10", tickvals=cuisines, ticktext=ticks, tickangle=0, showgrid=False)
    fig.update_yaxes(title="Borough", autorange="reversed", showgrid=False)
    fig.update_layout(margin={"l": 110, "r": 18, "t": 8, "b": 80})
    return fig, cuisines


def select_state(trigger, borough, click_data, selected, heat_cuisines):
    """A small state reducer; no shared mutable selection between browser sessions."""
    if trigger == "reset":
        return "All NYC", None
    if trigger == "heatmap" and click_data and click_data.get("points"):
        point = click_data["points"][0]
        if point.get("y") in BOROUGHS and point.get("x") in heat_cuisines:
            return point["y"], point["x"]
    if trigger == "borough":
        selected = None
    return borough if borough in ["All NYC", *BOROUGHS] else "All NYC", selected


def create_app(frame=None, metadata=None):
    if frame is None:
        frame, metadata = load_data()
    metadata = metadata or {}
    heatmap, heat_cuisines = heatmap_figure(frame)
    app = Dash(__name__, title="A Taste of NYC", assets_folder=str(ROOT / "assets"))
    app.layout = html.Main([
        html.Header([
            html.Div([html.P("NEW YORK CITY · RESTAURANT INSPECTIONS", className="eyebrow"),
                      html.H1("A Taste of NYC"),
                      html.P("Explore cuisine, restaurant counts, and inspection grades across the five boroughs.", className="intro")]),
            html.Div([html.Span("DATA SNAPSHOT"), html.Strong(metadata.get("download_date", "Unknown"))], className="snapshot"),
        ]),
        html.Div([
            html.Div([html.Label("Borough", htmlFor="borough"),
                      dcc.Dropdown(id="borough", options=["All NYC", *BOROUGHS], value="All NYC", clearable=False, searchable=False)], className="filter"),
            html.Button("Reset", id="reset", n_clicks=0),
            html.Div([html.Span("CURRENT SELECTION", className="selection-label"), html.Strong(id="selection")], className="selection", **{"aria-live": "polite"}),
            html.P("Click a heatmap cell to link the views.", className="hint"),
        ], className="controls"),
        dcc.Store(id="selected-cuisine", data=None),
        html.Div(id="metrics", className="metrics"),
        html.Div([
            html.Section([
                html.Div([html.Span("RQ3", className="rq"), html.H2("Cuisine size & Grade A percentage")], className="chart-title"),
                html.P(id="scatter-scope", className="chart-subtitle"),
                dcc.Graph(id="scatter", config=CONFIG, responsive=True, style={"height": "580px"}, className="scatter-plot"),
                html.P("Each point is a cuisine. Hollow points have fewer than 10 graded restaurants. Hover for sample size.", className="figure-note"),
                html.P(id="scatter-note", className="figure-note"),
            ], className="panel scatter-panel"),
            html.Div([
                html.Section([
                    html.Div([html.Span("RQ1", className="rq"), html.H2(id="bar-title")], className="chart-title"),
                    html.P(id="bar-scope", className="chart-subtitle"),
                    dcc.Graph(id="bar", config=CONFIG, responsive=True, style={"height": "285px"}, className="bar-plot"),
                ], className="panel"),
                html.Section([
                    html.Div([html.Span("RQ2", className="rq"), html.H2("Cuisine share by borough · NYC top 10")], className="chart-title"),
                    html.P("Share of all restaurants in each borough · darker = larger share", className="chart-subtitle"),
                    dcc.Graph(id="heatmap", figure=heatmap, config=CONFIG, responsive=True, style={"height": "255px"}, className="heatmap-plot"),
                ], className="panel"),
            ], className="right-column"),
        ], className="chart-grid"),
        html.Footer([
            html.P("Counts represent unique restaurants. Grade A percentages use each restaurant’s latest available A/B/C graded inspection."),
            html.P("Unrated restaurants count toward totals, but not the Grade A denominator. Heatmap shares use all cuisines in each borough; the heatmap remains citywide when filtering."),
            html.P(["Source: ", html.A("NYC DOHMH Restaurant Inspection Results", href=SOURCE_URL, target="_blank", rel="noreferrer"),
                    f" · Downloaded {metadata.get('download_date', 'unknown')} · Active establishments in the source snapshot, not an all-time census."]),
        ]),
    ], className="page")

    @app.callback(
        Output("borough", "value"), Output("selected-cuisine", "data"),
        Output("heatmap", "clickData"), Output("scatter", "figure"), Output("bar", "figure"),
        Output("selection", "children"), Output("metrics", "children"),
        Output("scatter-scope", "children"), Output("bar-scope", "children"),
        Output("bar-title", "children"), Output("scatter-note", "children"),
        Input("borough", "value"), Input("heatmap", "clickData"), Input("reset", "n_clicks"),
        State("selected-cuisine", "data"),
    )
    def update(borough, click_data, reset_clicks, selected):
        borough, selected = select_state(ctx.triggered_id, borough, click_data, selected, heat_cuisines)
        subset = frame if borough == "All NYC" else frame[frame.borough.eq(borough)]
        summary = cuisine_summary(subset)
        bar, extra = bar_figure(summary, selected)
        rated = int(subset.grade.isin(["A", "B", "C"]).sum())
        grade_a = int(subset.grade.eq("A").sum())
        metrics = [html.Div([html.Strong(value), html.Span(label)]) for label, value in [
            ("Restaurants", f"{len(subset):,}"), ("With A/B/C grades", f"{rated:,}"),
            ("Grade A · of graded restaurants", f"{grade_a / rated:.1%}" if rated else "No data")]]
        omitted = int(summary.rated.eq(0).sum())
        note = f"{omitted} cuisine(s) with no valid grade are not plotted; they remain in counts. No minimum sample filter."
        if selected:
            row = summary[summary.cuisine.eq(selected)]
            if row.empty:
                note = f"{selected}: 0 restaurants; Grade A: no data. " + note
            elif int(row.iloc[0].rated) == 0:
                note = f"{selected}: Grade A unavailable (0 rated restaurants). " + note
        return (borough, selected, None, scatter_figure(summary, selected), bar,
                f"{borough} · {selected or 'All cuisines'}", metrics,
                f"{borough} · All cuisines with at least one valid A/B/C grade",
                f"{borough} · Ranked by unique restaurants" + (" · ◀ selected cuisine" if selected else ""),
                "Restaurant count · Top 10" + (" + selected cuisine" if extra else ""), note)

    return app


app = create_app()
server = app.server

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=int(os.environ.get("PORT", "8050")), debug=False)
