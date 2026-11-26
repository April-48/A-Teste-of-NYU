"""A Taste of NYC — three linked views of unique restaurants."""
from __future__ import annotations

import json
import math
import os
import textwrap
from html import escape
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
from dash import Dash, Input, Output, State, ctx, dcc, html

from prepare_data import BOROUGHS, SOURCE_URL
from borough_map import BoroughMap, register_view_callbacks
from palette import ABOVE, BELOW, SMALL_SAMPLE, BAR_BACKGROUND, SELECTED, HEAT_COLORS
from dashboard_ui import expand_button, ui_components, register_ui_callbacks

ROOT = Path(__file__).resolve().parent
MISSING_CUISINE = "Unknown"
SAMPLE_LIMITS = (1, 10, 25, 50, 100)
COUNT_RANGES = {"all": ("Any count", 0, None), "1-9": ("1–9 restaurants", 1, 9),
                "10-49": ("10–49 restaurants", 10, 49), "50-99": ("50–99 restaurants", 50, 99),
                "100-499": ("100–499 restaurants", 100, 499), "500+": ("500+ restaurants", 500, None)}
INK = "#172033"
CONFIG = {"displayModeBar": False, "responsive": True, "scrollZoom": False}
# Interrupt rather than queue rapid selections; redraw commits category/trace changes.
ANIMATION = {"mode": "immediate", "frame": {"duration": 180, "redraw": True},
             "transition": {"duration": 180, "easing": "cubic-in-out"}}


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
    figure.update_xaxes(title_font={"size": 16}, tickfont={"size": 14}, showline=True, linecolor="#cbd2d7")
    figure.update_yaxes(title_font={"size": 16}, tickfont={"size": 14})
    return figure


def count_cuisines(summary, count_range="all"):
    """Select cuisine identities; leave all restaurant/rate denominators intact."""
    if count_range == "all":
        return None
    _, low, high = COUNT_RANGES[count_range]
    mask = summary.restaurants.ge(low) & summary.cuisine.ne(MISSING_CUISINE)
    if high is not None:
        mask &= summary.restaurants.le(high)
    return tuple(sorted(summary.loc[mask, "cuisine"]))


def empty_figure(message, x_title=None, y_title=None):
    fig = base_figure()
    fig.update_xaxes(title=x_title)
    fig.update_yaxes(title=y_title)
    fig.add_annotation(text=message, x=0.5, y=0.5, xref="paper", yref="paper", showarrow=False)
    return fig


def scatter_labels(plotted, selected, benchmark, x_range, y_range, full=False):
    """Label the selection and up to three large cuisines, leaving crowded marks alone.

    Approximate text boxes on a conservative 320px-wide plot so labels remain
    sparse on laptops. These are presentation decisions, not data exclusions.
    """
    width, height = 320, 250
    visible = plotted[plotted.grade_a_pct.between(*y_range)]
    candidates = pd.concat([visible[visible.cuisine.eq(selected)],
                            visible[visible.cuisine.ne(selected) & (visible.rated >= 10)].head(3)])
    def project_position(row):
        return ((math.log10(float(row.restaurants)) - x_range[0]) / (x_range[1] - x_range[0]) * width,
                (y_range[1] - float(row.grade_a_pct)) / (y_range[1] - y_range[0]) * height)
    # Reserve the area occupied by the benchmark label, directly below its line.
    line_y = (y_range[1] - benchmark) / (y_range[1] - y_range[0]) * height
    occupied = ([(width - 265, height - 34, width, height)] if full else
                [(width - 208, line_y + 7, width, line_y + 30)])
    marks = [project_position(r) for r in visible.itertuples()]
    labels = {}
    for row in candidates.itertuples():
        x, y = project_position(row)
        label_width, label_height = len(row.cuisine) * 8, 19
        positions = {
            "top center": (x-label_width/2, y-12-label_height),
            "bottom center": (x-label_width/2, y+12),
            "middle right": (x+12, y-label_height/2),
            "middle left": (x-12-label_width, y-label_height/2),
        }
        for position, (left, top) in positions.items():
            box = (left, top, left+label_width, top+label_height)
            if left < 0 or box[2] > width or top < 0 or box[3] > height:
                continue
            if any(left < r+4 and box[2] > l-4 and top < b+4 and box[3] > t-4 for l,t,r,b in occupied):
                continue
            if any(left-4 < px < box[2]+4 and top-4 < py < box[3]+4 for px,py in marks):
                continue
            labels[row.cuisine] = position
            occupied.append(box)
            break
        else:
            if row.cuisine == selected:
                # A selected cuisine must remain identified, even in a dense cluster.
                labels[row.cuisine] = "bottom right" if x < width/2 else "bottom left"
                left = x+12 if x < width/2 else x-12-label_width
                occupied.append((left, y+12, left+label_width, y+12+label_height))
    return labels


def scatter_figure(summary, selected, scope="All NYC", min_graded=1, allowed=None):
    # The benchmark is a pooled restaurant-level rate, not a mean of cuisine rates.
    total_rated = int(summary.rated.sum())
    benchmark = float(summary.grade_a.sum() / total_rated) if total_rated else None
    plotted = summary[(summary.rated >= min_graded) & summary.cuisine.ne(MISSING_CUISINE)]
    if allowed is not None:
        plotted = plotted[plotted.cuisine.isin(allowed)]
    if plotted.empty:
        return empty_figure("No cuisines meet both count and graded-sample filters" if allowed is not None else "No recorded cuisines meet the graded-sample filter" if min_graded > 1 else "No recorded cuisines with A/B/C grades in this selection", "Restaurants (count) · log scale", "Grade A rate (%)")
    fig = base_figure()
    x_range = [math.log10(float(plotted.restaurants.min())) - 0.12,
               math.log10(float(plotted.restaurants.max())) + 0.18]
    focus_range, full_range = [0.78, 1.025], [-0.025, 1.18]
    selected_row = plotted[plotted.cuisine.eq(selected)]
    # A selected low-rate cuisine, or a low benchmark, must stay visible.
    full = bool(benchmark < 0.8 or plotted.grade_a_pct.max() < 0.8 or
                (not selected_row.empty and selected_row.iloc[0].grade_a_pct < 0.8))
    y_range = full_range if full else focus_range
    label_sets = {
        "focus": scatter_labels(plotted, selected, benchmark, x_range, focus_range),
        "full": scatter_labels(plotted, selected, benchmark, x_range, full_range, full=True),
    }
    labels = label_sets["full" if full else "focus"]
    groups = [(plotted[plotted.cuisine.ne(selected)], False), (plotted[plotted.cuisine.eq(selected)], True)]
    for rows, active in groups:
        if rows.empty:
            continue
        # Small samples get their own shape, regardless of the benchmark side.
        colors = [SMALL_SAMPLE if n < 10 else ABOVE if value >= benchmark else BELOW
                  for value, n in zip(rows.grade_a_pct, rows.rated)]
        symbols = ["square-open" if n < 10 else "triangle-up" if value >= benchmark else "circle"
                   for value, n in zip(rows.grade_a_pct, rows.rated)]
        relation = ["At or above overall" if value >= benchmark else "Below overall" for value in rows.grade_a_pct]
        custom = [[c, int(n), int(r), int(a), rel, scope] for c, n, r, a, rel in
                  zip(rows.cuisine, rows.restaurants, rows.rated, rows.grade_a, relation)]
        fig.add_trace(go.Scatter(
            x=rows.restaurants.tolist(), y=rows.grade_a_pct.tolist(), ids=rows.cuisine.tolist(),
            mode="markers+text",
            text=[escape(c) if c in labels else "" for c in rows.cuisine],
            textposition=[labels.get(c, "top center") for c in rows.cuisine],
            textfont={"color": INK if active else "#4a555c", "size": 14 if active else 13}, cliponaxis=True,
            customdata=custom,
            marker={"size": 14 if active else 9, "color": colors,
                    "opacity": 1,
                    "symbol": symbols,
                    "line": {"width": 3 if active else 1, "color": SELECTED if active else colors}},
            hovertemplate="<b>%{customdata[0]}</b><br>Borough: %{customdata[5]}<br>Restaurants: %{customdata[1]:,}<br>Rated (A/B/C): %{customdata[2]:,}<br>Grade A restaurants: %{customdata[3]:,}<br>Grade A: %{y:.1%}<br>%{customdata[4]}<extra></extra>"))
        if active and int(rows.iloc[0].rated) < 10:
            # Preserve the hollow small-sample square and add a matching navy outline.
            fig.add_trace(go.Scatter(x=rows.restaurants.tolist(), y=rows.grade_a_pct.tolist(),
                                    mode="markers", customdata=custom,
                                    hovertemplate="<b>%{customdata[0]}</b><br>Borough: %{customdata[5]}<br>Restaurants: %{customdata[1]:,}<br>Rated (A/B/C): %{customdata[2]:,}<br>Grade A restaurants: %{customdata[3]:,}<br>Grade A: %{y:.1%}<extra></extra>", marker={"size": 17,
                                    "symbol": symbols, "color": SELECTED, "line": {"width": 1.5}}))
    fig.add_hline(y=benchmark, line={"color": "#45515c", "width": 1.8, "dash": "dash"}, layer="below")
    # Full range compresses marks near the benchmark: keep its caption in the
    # lower-right open area, away from points and cuisine labels.
    captions = {
        "focus": {"y": benchmark, "yref": "y", "yanchor": "top", "yshift": -7,
                  "text": f"{escape(scope)} overall: <b>{benchmark:.1%}</b>"},
        "full": {"y": .03, "yref": "paper", "yanchor": "bottom", "yshift": 0,
                 "text": f"{escape(scope)} overall (dashed): <b>{benchmark:.1%}</b>"},
    }
    fig.add_annotation(x=1, xref="paper", **captions["full" if full else "focus"],
                       showarrow=False, xanchor="right",
                       font={"size": 13, "color": "#45515c"}, bgcolor="white", borderpad=2)
    ticks = [m * 10**e for e in range(-1, 6) for m in (1, 3)
             if x_range[0] <= math.log10(m * 10**e) <= x_range[1] and m * 10**e >= 1]
    if len(ticks) < 2:
        ticks = sorted(set(plotted.restaurants.astype(int)))
    fig.update_xaxes(title="Restaurants (count) · log scale", range=x_range,
                     tickmode="array", tickvals=ticks, ticktext=[f"{n:,}" for n in ticks], type="log")
    fig.update_yaxes(title="Grade A rate (%)", range=y_range, tickformat=".0%", dtick=0.2 if full else 0.05)
    outside = int((plotted.grade_a_pct < focus_range[0]).sum())
    zoom_note = f"{outside} cuisines below focus · Choose Full 0–100%" if outside else "All cuisines fit within the zoom"
    fig.add_annotation(x=0, y=1.02, xref="paper", yref="paper", xanchor="left", yanchor="bottom",
                       text=zoom_note, visible=not full, showarrow=False,
                       font={"size": 11, "color": "#59645f"})
    views = {}
    for mode, axis_range, tick_step in [("focus", focus_range, .05), ("full", full_range, .2)]:
        label_map = label_sets[mode]
        views[mode] = {
            "text": [[escape(row[0]) if row[0] in label_map and trace.mode == "markers+text" else ""
                      for row in trace.customdata] for trace in fig.data],
            "textposition": [[label_map.get(row[0], "top center") for row in trace.customdata]
                             for trace in fig.data],
            "range": axis_range, "tick_step": tick_step, "caption": captions[mode],
        }
    # Presentation states travel with the figure, so the local dropdown works
    # unchanged in Dash and in the fixed-snapshot public export.
    fig.update_layout(margin={"l": 62, "r": 18, "t": 26, "b": 48},
                      meta={"scatter_ranges": views, "auto_full": full,
                            "range_mode": "full" if full else "focus", "range_synced": False})
    return fig


def bar_figure(summary, selected, scope="All NYC", allowed=None):
    total = int(summary.restaurants.sum())  # Includes unrecorded cuisines.
    summary = summary[summary.cuisine.ne(MISSING_CUISINE)].copy()
    summary["rank"] = range(1, len(summary) + 1)
    if allowed is not None:
        summary = summary[summary.cuisine.isin(allowed)]
    if summary.empty:
        return empty_figure("No restaurants in this selection", "Restaurants (count)", "Cuisine"), False
    top = summary.head(10)
    extra = bool(selected and selected not in top.cuisine.values and selected in summary.cuisine.values)
    if extra:
        top = pd.concat([top, summary[summary.cuisine.eq(selected)]])
    fig = base_figure()
    fig.add_trace(go.Bar(
        x=top.restaurants.tolist(), y=top.cuisine.tolist(), ids=top.cuisine.tolist(), orientation="h",
        marker_color=[SELECTED if c == selected else BAR_BACKGROUND for c in top.cuisine],
        customdata=[[c, int(n), float(n / total), scope, int(rank)] for c, n, rank in zip(top.cuisine, top.restaurants, top["rank"])],
        text=[f"{n:,} · Rank {rank}" if extra and c == selected else f"{n:,}"
              for c, n, rank in zip(top.cuisine, top.restaurants, top["rank"])],
        textposition="outside", textfont={"size": 14}, constraintext="none", cliponaxis=False,
        hovertemplate="<b>%{customdata[0]}</b><br>Borough: %{customdata[3]}<br>Restaurants: %{x:,}<br>Share of all restaurants: %{customdata[2]:.1%}<br>Rank: %{customdata[4]}<extra></extra>"))
    fig.update_yaxes(title={"text": "Cuisine", "standoff": 14}, autorange="reversed", showgrid=False, automargin=True,
                     tickvals=top.cuisine.tolist(),
                     ticktext=[f"<b>{escape(c)}</b>" if c == selected else escape(c)
                               for c in top.cuisine], tickfont={"size": 14})
    fig.update_xaxes(title="Restaurants (count)", range=[0, float(top.restaurants.max()) * 1.22], tickformat=",d")
    fig.update_layout(margin={"l": 196, "r": 38, "t": 6, "b": 40}, bargap=0.3)
    fig.update_xaxes(title_font={"size": 16}, tickfont={"size": 14}, nticks=5, title_standoff=12)
    fig.update_yaxes(tickfont={"size": 14})
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
            return "#000000" if luminance > 0.179 else "#ffffff"
    return "#ffffff"


def heatmap_figure(frame, borough="All NYC", selected=None, allowed=None):
    if frame.empty:
        return empty_figure("No restaurant data available", "Cuisine", "Borough"), []
    summary = cuisine_summary(frame)
    recorded = summary[summary.cuisine.ne(MISSING_CUISINE)]
    eligible = recorded if allowed is None else recorded[recorded.cuisine.isin(allowed)]
    cuisines = eligible.head(10).cuisine.tolist()
    if selected in eligible.cuisine.values and selected not in cuisines:
        cuisines.append(selected)
    if not cuisines:
        return empty_figure("No recorded cuisines available", "Cuisine", "Borough"), []
    counts = pd.crosstab(frame.borough, frame.cuisine).reindex(index=BOROUGHS, columns=cuisines, fill_value=0)
    totals = frame.groupby("borough").CAMIS.nunique().reindex(BOROUGHS, fill_value=0)
    shares = counts.div(totals.replace(0, float("nan")), axis=0)
    detail = [[[b, c, int(counts.loc[b, c]), int(totals[b])] for c in cuisines] for b in BOROUGHS]
    z = [[None if pd.isna(v) else float(v) for v in row] for row in shares.values]
    all_counts = pd.crosstab(frame.borough, frame.cuisine).reindex(index=BOROUGHS, columns=recorded.cuisine, fill_value=0)
    maximum = max(0.01, float(all_counts.div(totals.replace(0, float("nan")), axis=0).max().max()))
    maximum = math.ceil(maximum * 20) / 20
    fig = base_figure()
    fig.add_trace(go.Heatmap(
        x=cuisines, y=BOROUGHS, z=z, customdata=detail, zmin=0,
        zmax=maximum,
        colorscale=HEAT_COLORS,
        xgap=2, ygap=2, hoverongaps=False,
        # A side title leaves enough space for percentage ticks in a compact card.
        colorbar={"title": {"text": "Share (%)", "side": "right", "font": {"size": 12}},
                  "tickformat": ".0%", "tickfont": {"size": 12}, "thickness": 12,
                  "len": 1, "xpad": 8, "tickvals": [0, maximum / 2, maximum]},
        hovertemplate="<b>%{customdata[0]} · %{customdata[1]}</b><br>Restaurants: %{customdata[2]:,}<br>Share of borough: %{z:.1%}<br>All borough restaurants: %{customdata[3]:,}<extra></extra>"))
    for i, boro in enumerate(BOROUGHS):
        for j, cuisine in enumerate(cuisines):
            value = z[i][j]
            fig.add_annotation(x=cuisine, y=boro, text=f"{value:.1%}" if value is not None else "—",
                               showarrow=False, captureevents=False,
                               font={"size": 14, "color": heat_text_color(value / maximum) if value is not None else INK})
    if selected in cuisines:
        x = cuisines.index(selected)
        # Every borough in the selected cuisine gets a thin outline.
        for y, boro in enumerate(BOROUGHS):
            active = boro == borough
            for inset, color, width in [(0.49, SELECTED, 3 if active else 1),
                                        (0.44, "white", 1.5 if active else 0.6)]:
                fig.add_shape(type="rect", x0=x-inset, x1=x+inset, y0=y-inset, y1=y+inset,
                              xref="x", yref="y", line={"color": color, "width": width}, fillcolor="rgba(0,0,0,0)")
    # Wrap longer category labels; full category names remain in hover.
    labels = {"Coffee/Tea": "Coffee /<br>Tea", "Latin American": "Latin<br>American", "Juice, Smoothies, Fruit Salads": "Juice / Smoothies",
              "Bakery Products/Desserts": "Bakery /<br>Desserts"}
    ticks = [escape(labels.get(c, textwrap.shorten(c, width=22, placeholder="…"))).replace("&lt;br&gt;", "<br>") for c in cuisines]
    ticks = [f"<b>{t}</b>" if c == selected else t for c, t in zip(cuisines, ticks)]
    fig.update_xaxes(title={"text": "Cuisine", "standoff": 6}, tickvals=cuisines, ticktext=ticks, tickangle=0, showgrid=False, showline=False,
                     tickfont={"size": 14})
    fig.update_yaxes(title={"text": "Borough", "standoff": 14}, autorange="reversed", showgrid=False, tickvals=BOROUGHS,
                     ticktext=[f"<b>{b}</b>" if b == borough else b for b in BOROUGHS], tickfont={"size": 14})
    fig.update_layout(margin={"l": 120, "r": 12, "t": 6, "b": 72})
    return fig, cuisines


def select_state(trigger, borough, click_data, selected, heat_cuisines):
    """A small state reducer; no shared mutable selection between browser sessions."""
    if trigger == "reset":
        return "All NYC", None
    if trigger == "borough-map" and click_data and click_data.get("points"):
        point = click_data["points"][0]
        index = point.get("curveNumber")
        if isinstance(index, int) and 0 <= index < len(BOROUGHS):
            return BOROUGHS[index], selected
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
    return borough if borough in ["All NYC", *BOROUGHS] else "All NYC", selected


def metrics_view(summary, selected, borough, total, rated):
    """Headline card; all denominators describe the full selected scope."""
    scope = html.Span(f"Scope totals · {borough}: {total:,} restaurants · {rated:,} with A/B/C grades", className="scope-total")
    def metric(value, label):
        return html.Div([html.Strong(value, className="metric-value"),
                         html.Span(label, className="metric-label")], className="metric-cell")
    rows = summary[summary.cuisine.eq(selected)]
    if selected:
        row = rows.iloc[0] if not rows.empty else None
        count = int(row.restaurants) if row is not None else 0
        sample = int(row.rated) if row is not None else 0
        rate = f"{row.grade_a_pct:.1%}" if sample else "—"
        share = f"{count / total:.1%}" if total else "—"
        context = html.Div([html.Strong(selected), html.Span("Cuisine focus" if count else "No restaurants in this borough")], className="metric-context")
        cells = [metric(f"{count:,}", "Restaurants"),
                 metric(rate, f"Grade A · {sample:,} graded" if sample else "No A/B/C graded sample"),
                 metric(share, "Share of NYC" if borough == "All NYC" else "Share of borough")]
    else:
        rate = f"{summary.grade_a.sum() / rated:.1%}" if rated else "—"
        context = html.Div([html.Strong("All cuisines"), html.Span(borough)], className="metric-context")
        cells = [metric(f"{total:,}", "Restaurants"), metric(f"{rated:,}", "Graded (A/B/C)"), metric(rate, "Overall Grade A")]
    return [scope, html.Div([context, *cells], className="metrics-main")]


def register_scatter_callbacks(app):
    """One presentation callback owns the rendered scatter; source data stay immutable."""
    app.clientside_callback(
        """function(mode, figure) {
            const no = window.dash_clientside.no_update;
            if (!figure || !figure.layout) return [no, no, ""];
            const meta = figure.layout.meta || {};
            const changed = (window.dash_clientside.callback_context.triggered || [])
                .some(t => t.prop_id === "scatter-range.value");
            const effective = changed ? mode : meta.reset_range ? "focus" :
                meta.auto_full ? "full" : mode || "focus";
            if (!(meta.scatter_ranges || {})[effective])
                return [structuredClone(figure), meta.reset_range ? "focus" : no, ""];
            const next = structuredClone(figure);
            const view = next.layout.meta.scatter_ranges[effective];
            next.data.forEach((trace, i) => {
                trace.text = view.text[i].slice();
                trace.textposition = view.textposition[i].slice();
            });
            next.layout.yaxis.range = view.range.slice();
            next.layout.yaxis.dtick = view.tick_step;
            Object.assign(next.layout.annotations[0], view.caption);
            const hint = String(next.layout.annotations[1].text || "");
            const hidden = hint.match(/^([0-9]+) cuisines below focus/);
            const note = effective === "focus" && hidden
                ? hidden[1] + " below focus · Full 0–100% shows all" : "";
            next.layout.annotations[1].visible = false;
            next.layout.margin.t = 10;
            next.layout.meta.range_mode = effective;
            next.layout.meta.range_synced = true;
            return [next, effective === mode ? no : effective, note];
        }""",
        Output("scatter", "figure"), Output("scatter-range", "value"),
        Output("scatter-range-note", "children"),
        Input("scatter-range", "value"), Input("scatter-source", "data"),
        prevent_initial_call=True)


def create_app(frame=None, metadata=None):
    if frame is None:
        frame, metadata = load_data()
    metadata = metadata or {}
    heatmap, heat_cuisines = heatmap_figure(frame)
    map_model = BoroughMap(frame, BOROUGHS, HEAT_COLORS, MISSING_CUISINE)
    initial_map, initial_map_cuisine = map_model.figure()
    all_cuisines = set(frame.loc[frame.cuisine.ne(MISSING_CUISINE), "cuisine"])
    summaries = {b: cuisine_summary(frame if b == "All NYC" else frame[frame.borough.eq(b)]) for b in ["All NYC", *BOROUGHS]}
    app = Dash(__name__, title="A Taste of NYC", assets_folder=str(ROOT / "assets"))
    app.layout = html.Main([
        html.Header([
            html.Div([html.H1("A Taste of NYC"),
                      html.P("Explore New York’s cuisines and how their inspection grades compare.", className="intro")]),
        ]),
        html.Div([
            html.Span("Filters", className="filters-heading"),
            html.Div([html.Label("Borough", htmlFor="borough"),
                      dcc.Dropdown(id="borough", options=["All NYC", *BOROUGHS], value="All NYC", clearable=False, searchable=False)], className="filter"),
            html.Div([html.Label("Cuisine focus", htmlFor="cuisine-focus"),
                      dcc.Dropdown(id="cuisine-focus", options=sorted(all_cuisines), value=None,
                                   placeholder="Search cuisines…", clearable=True, searchable=True)], className="filter cuisine-filter"),
            html.Div([html.Label("Restaurants per cuisine", htmlFor="count-filter"),
                      dcc.Dropdown(id="count-filter", options=[{"label": v[0], "value": k} for k, v in COUNT_RANGES.items()],
                                   value="all", clearable=False, searchable=False)], className="filter count-filter",
                     title="Unique restaurants per cuisine in the selected borough. Filters all three charts."),
            html.Button("Reset", id="reset", n_clicks=0),
            html.Div([html.Strong(id="selection")], className="selection sr-only", **{"aria-live": "polite"}),
            html.Span(id="count-status", className="count-status"),
            html.P("Click any chart to select a cuisine.", className="hint"),
        ], className="controls"),
        html.Div(id="metrics", className="metrics", **{"aria-live": "polite"}),
        dcc.Store(id="selected-cuisine", data=None),
        dcc.Store(id="scatter-source"),
        dcc.Store(id="map-default-cuisine", data=initial_map_cuisine),
        html.Div([
            html.Section([
                html.Div([html.H2("Cuisine size & inspection grades"), expand_button("scatter", "scatter plot")], className="chart-title plot-heading"),
                html.P("RQ1 · How does cuisine size relate to Grade A rate?", className="research-question"),
                html.P(id="scatter-scope", className="chart-subtitle"),
                html.Div([
                    html.Span("Scatter only", className="scatter-only"),
                    html.Div([
                        html.Label("Y-axis range", htmlFor="scatter-range"),
                        dcc.Dropdown(id="scatter-range", options=[
                            {"label": "Focus 80–100%", "value": "focus"},
                            {"label": "Full 0–100%", "value": "full"}],
                            value="focus", clearable=False, searchable=False),
                    ], className="scatter-control", title="Focus compares rates near 80–100%; Full shows every rate."),
                    html.Div([
                        html.Label("Graded sample", htmlFor="sample-filter"),
                        dcc.Dropdown(id="sample-filter", options=[
                            {"label": "All rated cuisines" if n == 1 else f"{n}+ graded restaurants", "value": n}
                            for n in SAMPLE_LIMITS], value=1, clearable=False, searchable=False),
                        html.Div(id="sample-status", className="sample-feedback", **{"aria-live": "polite"}),
                    ], className="scatter-control", title="Minimum A/B/C-graded restaurants per cuisine. Scatter only."),
                ], className="scatter-controls"),
                html.Div([
                    html.Span([html.Img(src="assets/legend-triangle.svg", className="key-mark", alt=""), "At/above overall"]),
                    html.Span([html.Img(src="assets/legend-circle.svg", className="key-mark", alt=""), "Below overall"]),
                    html.Span([html.Img(src="assets/legend-square-open.svg", className="key-mark", alt=""),
                               "<10 graded"]),
                ], className="plot-key"),
                dcc.Graph(id="scatter", clear_on_unhover=True, config=CONFIG, responsive=True, animate=True, animation_options=ANIMATION, className="scatter-plot"),
                html.Div([
                    html.Div([
                        html.Span(id="scatter-range-note", **{"aria-live": "polite"}),
                    ], className="scatter-status"),
                    html.P("Log X uses count ratios. Grade A reflects inspections, not taste.", className="reading-note"),
                ], className="scatter-footer"),
            ], className="panel scatter-panel"),
            html.Div([
                html.Section([
                    html.Div([html.H2(id="bar-title"), expand_button("bar", "restaurant ranking")], className="chart-title plot-heading"),
                    html.P("RQ2 · Which cuisines have the most restaurants?", className="research-question"),
                    html.P(id="bar-scope", className="chart-subtitle"),
                    html.P("Click a bar to highlight that cuisine across all three views.", className="interaction-hint"),
                    dcc.Graph(id="bar", clear_on_unhover=True, config=CONFIG, responsive=True, animate=True, animation_options=ANIMATION, className="bar-plot"),
                ], className="panel"),
                html.Section([
                    html.Div([
                        html.H2("Cuisine share by borough", id="heatmap-title"),
                        html.Div([
                        html.Div(dcc.RadioItems(id="borough-view", options=[
                            {"label":"Heatmap", "value":"heatmap"}, {"label":"Map", "value":"map"}],
                            value="heatmap", inline=True, className="view-toggle"),
                            role="group", **{"aria-label":"Borough view"}),
                            expand_button("borough", "borough view"),
                        ], className="plot-actions"),
                    ], className="chart-title view-heading"),
                    html.P("RQ3 · How does cuisine share vary across boroughs?", className="research-question"),
                    html.Div([
                        html.P(f"NYC top 10 · % of all borough restaurants · Shared scale: 0–{map_model.maximum:.0%}", id="heatmap-scope", className="chart-subtitle"),
                        dcc.Graph(id="heatmap", clear_on_unhover=True, figure=heatmap, config=CONFIG, responsive=True, className="heatmap-plot"),
                    ], id="heatmap-view", style={"display":"block"}),
                    html.Div([
                        html.P("Choose a cuisine in Filters to compare borough shares.",
                               id="map-cuisine", className="chart-subtitle"),
                        dcc.Graph(id="borough-map", clear_on_unhover=True, figure=initial_map, config=CONFIG, responsive=True, className="map-plot"),
                    ], id="map-view", style={"display":"none"}),
                ], id="borough-panel", className="panel borough-panel heatmap-mode"),
            ], className="right-column"),
        ], className="chart-grid"),
        *ui_components(),
        html.Footer([
            html.P("Counts represent unique restaurants. Grade A percentages use each restaurant’s latest available A/B/C graded inspection."),
            html.A("NYC DOHMH Restaurant Inspection Results", href=SOURCE_URL, target="_blank", rel="noreferrer"),
            f" · Downloaded {metadata.get('download_date', 'unknown')}",
        ]),
    ], className="page")

    @app.callback(
        Output("borough", "value"), Output("selected-cuisine", "data"),
        Output("heatmap", "clickData"), Output("scatter-source", "data"), Output("bar", "figure"),
        Output("selection", "children"), Output("metrics", "children"),
        Output("scatter-scope", "children"), Output("bar-scope", "children"),
        Output("bar-title", "children"),
        Output("heatmap", "figure"),
        Output("bar", "clickData"), Output("scatter", "clickData"),
        Output("sample-filter", "value"), Output("sample-status", "children"), Output("heatmap-title", "children"),
        Output("cuisine-focus", "value"), Output("cuisine-focus", "options"),
        Output("count-filter", "value"), Output("count-status", "children"), Output("heatmap-scope", "children"),
        Output("borough-map", "figure"), Output("borough-map", "clickData"),
        Output("map-cuisine", "children"), Output("map-default-cuisine", "data"),
        Input("borough", "value"), Input("heatmap", "clickData"), Input("reset", "n_clicks"),
        Input("bar", "clickData"), Input("scatter", "clickData"), Input("sample-filter", "value"),
        Input("cuisine-focus", "value"),
        Input("count-filter", "value"), Input("borough-map", "clickData"),
        State("selected-cuisine", "data"), State("borough-view", "value"),
    )
    def update(borough, click_data, reset_clicks, bar_click, scatter_click, sample_filter, cuisine_focus, count_filter, map_click, selected, view_mode):
        trigger = ctx.triggered_id
        click = {"heatmap": click_data, "bar": bar_click, "scatter": scatter_click, "borough-map": map_click}.get(trigger)
        borough, selected = select_state(trigger, borough, click, selected, all_cuisines)
        if trigger == "cuisine-focus":
            selected = cuisine_focus if cuisine_focus in all_cuisines else None
        minimum = sample_filter if sample_filter in SAMPLE_LIMITS and trigger != "reset" else 1
        subset = frame if borough == "All NYC" else frame[frame.borough.eq(borough)]
        summary = summaries[borough]
        count_filter = count_filter if count_filter in COUNT_RANGES and trigger != "reset" else "all"
        allowed = count_cuisines(summary, count_filter)
        if allowed is not None and selected not in allowed:
            if trigger in ("heatmap", "borough-map") and selected:
                # A heatmap click changes borough; keep the clicked cuisine visible.
                count_filter, allowed = "all", None
            else:
                selected = None
        cuisine_options = [{"label": c, "value": c} for c in sorted(all_cuisines if allowed is None else allowed)]
        bar, extra = bar_figure(summary, selected, borough, allowed)
        filtered = summary if allowed is None else summary[summary.cuisine.isin(allowed)]
        rated = int(subset.grade.isin(["A", "B", "C"]).sum())
        metrics = metrics_view(summary, selected, borough, len(subset), rated)
        omitted = int((filtered.rated.eq(0) & filtered.cuisine.ne(MISSING_CUISINE)).sum())
        hidden = int(((filtered.rated > 0) & (filtered.rated < minimum) & filtered.cuisine.ne(MISSING_CUISINE)).sum())
        visible = int(((filtered.rated >= minimum) & filtered.cuisine.ne(MISSING_CUISINE)).sum())
        sample_status = f"{visible} eligible cuisines · {hidden} hidden by sample filter"
        if omitted:
            sample_status += (" · " if sample_status else "") + f"{omitted} with no grade not plotted"
        if selected:
            row = summary[summary.cuisine.eq(selected)]
            if row.empty:
                sample_status += (" · " if sample_status else "") + f"{selected}: no restaurants in this borough"
            elif int(row.iloc[0].rated) == 0:
                sample_status += (" · " if sample_status else "") + f"{selected}: no valid grade"
            elif int(row.iloc[0].rated) < minimum:
                sample_status += f" · {selected} is hidden ({int(row.iloc[0].rated)} graded); lower the sample minimum to see it"
        heatmap, displayed_heat = heatmap_figure(frame, borough, selected, allowed)
        map_plot, map_cuisine = map_model.figure(borough, selected, allowed)
        count_label = COUNT_RANGES[count_filter][0]
        count_status = (f"{len(allowed)} cuisines with {count_label.lower()} in {borough} · Applies to all three charts"
                        if allowed is not None else "")
        scatter = scatter_figure(summary, selected, borough, minimum, allowed)
        scatter.update_layout(meta={**(scatter.layout.meta or {}), "reset_range": trigger == "reset"})
        return (borough, selected, None, scatter, bar,
                f"{borough} · {selected or ('All matching cuisines' if allowed is not None else 'All cuisines')}", metrics,
                f"{borough} · Each mark is a cuisine" + (f" · {count_label}" if allowed is not None else ""),
                f"{borough} · Top 10 by restaurant count" + (" within range" if allowed is not None else ""),
                "Most common cuisines" + (" · + selected" if extra else ""),
                heatmap,
                None, None, minimum, sample_status,
                "Cuisine share by borough" + (" · + selected" if len(displayed_heat) > 10 else ""),
                selected, cuisine_options, count_filter, count_status,
                ("NYC top 10 matching range" if allowed is not None else "NYC top 10") + f" · % of all borough restaurants · Shared scale: 0–{map_model.maximum:.0%}",
                map_plot, None, (f"{map_cuisine} · % of all borough restaurants · Shared scale: 0–{map_model.maximum:.0%} · Click a borough"
                                 if map_cuisine else "Choose a cuisine in Filters to compare borough shares."), map_cuisine)

    register_view_callbacks(app)
    register_scatter_callbacks(app)
    register_ui_callbacks(app)
    return app


app = create_app()
server = app.server

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=int(os.environ.get("PORT", "8050")), debug=False)
