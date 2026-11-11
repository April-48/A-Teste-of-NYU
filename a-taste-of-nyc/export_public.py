"""Export this fixed snapshot as an interactive, serverless Dash site.

Python remains the source of truth: every supported UI state is evaluated by
the real Dash callback. The browser retrieves the resulting figures instead
of POSTing to a Python server. Re-run after changing data, charts or controls.
Usage: python export_public.py /absolute/path/to/site/dist
"""
from __future__ import annotations

import hashlib
import json
import re
import shutil
import sys
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlsplit

import dash
from dash import ClientsideFunction, Dash, Input, State

import app as source


def export(destination):
    destination = Path(destination).resolve()
    destination.mkdir(parents=True, exist_ok=True)
    frame, metadata = source.load_data()
    boroughs = ["All NYC", *source.BOROUGHS]
    cuisines = [None, *sorted(set(frame.cuisine) - {source.MISSING_CUISINE})]
    summaries = {b: source.cuisine_summary(frame if b == "All NYC" else frame[frame.borough.eq(b)]) for b in boroughs}
    # Memoize unchanged figure components during export; each cache is scoped to
    # this one immutable snapshot. This does not alter the normal Dash app.
    original_bar, original_heat = source.bar_figure, source.heatmap_figure
    cached_bar = lru_cache(None)(lambda scope, selected: original_bar(summaries[scope], selected, scope))
    cached_heat = lru_cache(None)(lambda boro, selected: original_heat(frame, boro, selected))
    source.bar_figure = lambda summary, selected, scope="All NYC": cached_bar(scope, selected)
    source.heatmap_figure = lambda data, borough="All NYC", selected=None: cached_heat(borough, selected)

    key, callback = next(iter(source.app.callback_map.items()))
    outputs = callback["output"]
    public = Dash("nyc_public", title="A Taste of NYC", assets_folder=str(source.ROOT / "assets"))
    public.layout = source.app.layout
    public.clientside_callback(
        ClientsideFunction(namespace="nyc_public", function_name="update"),
        outputs,
        [Input(i["id"], i["property"]) for i in callback["inputs"]],
        [State(i["id"], i["property"]) for i in callback["state"]],
    )
    web = public.server.test_client()
    html = web.get("/").data.decode()
    html = html.replace('<script id="_dash-renderer"', '<script src="/public-callback.js"></script>\n<script id="_dash-renderer"')
    (destination / "index.html").write_text(html)
    shutil.copyfile(source.ROOT / "public" / "callback.js", destination / "public-callback.js")
    for route in ("/_dash-layout", "/_dash-dependencies", "/_favicon.ico"):
        response = web.get(route)
        assert response.status_code == 200, route
        name = route.lstrip("/") + (".json" if route.startswith("/_dash-") else "")
        (destination / name).write_bytes(response.data)
    shutil.copytree(source.ROOT / "assets", destination / "assets", dirs_exist_ok=True)

    # Dynamic Dash chunks use their normal package filenames; initial script
    # tags have fingerprinted filenames. Include both, with no CDN dependency.
    package = Path(dash.__file__).parent
    suite = destination / "_dash-component-suites" / "dash"
    for relative in ("dcc", "html", "dash_table", "deps", "dash-renderer/build"):
        for asset in (package / relative).rglob("*"):
            if asset.is_file() and asset.suffix in (".js", ".css", ".woff", ".woff2") and not asset.name.endswith(".dev.js"):
                target = suite / asset.relative_to(package)
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(asset, target)
    for url in re.findall(r'(?:src|href)="([^"\s]+)"', html):
        route = urlsplit(url).path
        if route.startswith("/_dash-component-suites/"):
            response = web.get(url)
            assert response.status_code == 200, url
            target = destination / route.lstrip("/")
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(response.data)
    import plotly
    plotly_file = Path(plotly.__file__).parent / "package_data" / "plotly.min.js"
    target = destination / "_dash-component-suites/plotly/package_data/plotly.min.js"
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(plotly_file, target)

    objects, states = destination / "objects", destination / "states"
    objects.mkdir(exist_ok=True)
    states.mkdir(exist_ok=True)
    saved = set()

    def store_object(value):
        # Content-addressing shares figures/options across UI states. Templates
        # are shared separately without changing any Plotly layout properties.
        if isinstance(value, dict) and "data" in value and "layout" in value:
            template = value["layout"].pop("template", None)
            if template is not None:
                value["layout"]["template"] = store_object(template)
        data = json.dumps(value, separators=(",", ":"), ensure_ascii=False).encode()
        digest = hashlib.sha256(data).hexdigest()
        if digest not in saved:
            (objects / (digest + ".json")).write_bytes(data)
            saved.add(digest)
        return {"$object": digest}

    client = source.app.server.test_client()
    total = 0
    try:
        for bi, borough in enumerate(boroughs):
            for ci, cuisine in enumerate(cuisines):
                for minimum in source.SAMPLE_LIMITS:
                    values = [borough, None, 0, None, None, minimum, cuisine]
                    response = client.post("/_dash-update-component", json={
                        "output": key,
                        "outputs": [{"id": o.component_id, "property": o.component_property} for o in outputs],
                        "inputs": [dict(i, value=v) for i, v in zip(callback["inputs"], values)],
                        "state": [{"id": "selected-cuisine", "property": "data", "value": cuisine}],
                        "changedPropIds": ["cuisine-focus.value"],
                    })
                    assert response.status_code == 200, (borough, cuisine, minimum)
                    result = response.get_json()["response"]
                    ordered = [result[o.component_id][o.component_property] for o in outputs]
                    packed = [store_object(v) if isinstance(v, (dict, list)) else v for v in ordered]
                    (states / f"{bi}-{ci}-{minimum}.json").write_text(json.dumps(packed, separators=(",", ":")))
                    total += 1
            print(f"Exported {borough}: {total} callback states", flush=True)
    finally:
        source.bar_figure, source.heatmap_figure = original_bar, original_heat
    manifest = {"boroughs": boroughs, "cuisines": cuisines, "minimums": list(source.SAMPLE_LIMITS),
                "outputs": [{"id": o.component_id, "property": o.component_property} for o in outputs],
                "snapshot": metadata["download_date"], "states": total}
    (destination / "state-index.json").write_text(json.dumps(manifest))
    (destination / "_headers").write_text("/objects/*\n  Cache-Control: public, max-age=31536000, immutable\n/states/*\n  Cache-Control: no-cache\n")
    print(f"Complete: {total} states, {len(saved)} shared objects", flush=True)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("Usage: python export_public.py /absolute/path/to/site/dist")
    export(sys.argv[1])
