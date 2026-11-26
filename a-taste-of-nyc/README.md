# A Taste of NYC

[Open the live dashboard on GitHub Pages](https://april-48.github.io/A-Teste-of-NYU/)

## Run locally

Use Python 3.12 or newer. From this directory:

```sh
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

Open http://127.0.0.1:8050. On Windows, activate with `.venv\Scripts\activate`.

## Data and definitions

The source is [NYC DOHMH Restaurant Inspection Results](https://data.cityofnewyork.us/d/43nn-pn8j). The included snapshot was downloaded on November 9, 2026. It contains 31,360 unique restaurants, of which 24,804 have an A/B/C graded inspection under the cleaning rules.

`data/restaurants.csv` contains one row per CAMIS restaurant. `prepare_data.py` preserves the latest valid borough and cuisine independently and assigns the latest available A/B/C graded inspection separately. Restaurants without a known cuisine remain in population denominators but are excluded from cuisine comparisons. Download receipts, source metadata and the cleaning audit remain in `data/`.

Restaurant counts use unique CAMIS IDs. Grade A rate is Grade A restaurants divided by A/B/C-graded restaurants within the selected scope. Cuisine share is a cuisine's restaurant count divided by all restaurants in the corresponding borough. Missing grades are excluded from grade-rate denominators. Grade A reflects inspection results, not taste.

The map uses the included NYC DCP land boundaries, a local equirectangular projection and the same within-borough share values as the heatmap. It does not load external map tiles.

## Linked views and controls

- RQ1 scatter compares cuisine restaurant count on a log X axis with Grade A rate (%). Focus 80–100% and Full 0–100% are presentation options; the graded-sample threshold affects only this view. Hollow squares identify fewer than ten graded restaurants.
- RQ2 ranks the most common cuisines by restaurant count. A selected cuisine outside the top ten is also shown.
- RQ3 compares within-borough cuisine shares with a shared 0–20% color scale. Switch between the heatmap and geographic map. Map clicks update the borough without assigning an automatic cuisine.
- Borough, cuisine and restaurant-count controls coordinate the views. Click a chart to select a cuisine or borough. Rounded hover cards provide details. Each card has an Expand button; press Esc to close the overlay.

The desktop overview shares the available window height across the three cards. Narrower or shorter windows preserve natural scrolling to maintain legibility.

## Validation and static publication

```sh
python -m unittest -q
python export_public.py public-dist --base-path /A-Teste-of-NYU/
python verify_public.py public-dist
```

The exporter evaluates supported selections through the real Python callback. The browser retrieves the resulting numeric states and figures; it does not recompute inspection statistics. Export verification compares representative states and map clicks against the callback and checks every generated state reference.

The existing workflow in `../.github/workflows/pages.yml` runs these commands and publishes the static result to GitHub Pages. The source Dash application still runs locally as Python; GitHub Pages serves the exported interactive edition.

## Code map

`app.py` defines the charts and linked selection. `borough_map.py` provides the offline borough map and display toggle. `dashboard_ui.py` and `assets/dashboard-ui.js` provide shared expansion and tooltip behavior. `palette.py` stores the shared colors. `assets/style.css` styles the three-card layout. `prepare_data.py` documents the cleaning pipeline; `prepare_borough_map.py` prepares the supplied boundary files. The fixed-snapshot publication pipeline is implemented in `export_public.py`, `public/callback.js` and `verify_public.py`.

The implementation and documentation were developed with OpenAI Codex assistance. The restaurant data are real NYC Open Data. Automated checks are separate from classroom usability testing.
