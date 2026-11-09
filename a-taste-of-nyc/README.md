# A Taste of NYC

A working Python + Plotly Dash prototype with the proposal's **Option B** layout: scatter on the left, horizontal bar at upper right, and heatmap at lower right. The UI is in English for the classroom demonstration.

## Install and run

Use Python 3.12–3.14 (tested with Python 3.14 on macOS). From a fresh clone:

```sh
git clone https://github.com/April-48/A-Teste-of-NYU.git
cd A-Teste-of-NYU/a-taste-of-nyc
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

On Windows, replace the activation command with `.venv\Scripts\activate` and use `python` instead of `python3` if needed.

Open **http://127.0.0.1:8050**. Stop with **Ctrl+C**. To restart, activate the same environment, enter this folder and run `python app.py` again. The checked-in cleaned data lets the app start without downloading anything. Dependencies are installed once; charts and data are served locally without CDN dependencies. If port 8050 is occupied, macOS/Linux users can run `PORT=8051 python app.py` and open port 8051.

This is a local classroom prototype, not a publicly hosted application. GitHub Pages cannot run Python Dash. The source repository and these setup instructions are the runnable-code submission.

## Data source and snapshot

- Source: [NYC DOHMH Restaurant Inspection Results, 43nn-pn8j](https://data.cityofnewyork.us/d/43nn-pn8j).
- Actual download date: **November 9, 2026**, America/New_York.
- The portal's full CSV export failed during download. The successful fallback was the **same official Socrata dataset**, requesting all rows but projecting only `camis`, `boro`, `cuisine_description`, `inspection_date`, and `grade`; no row filters were used.
- **295,002 source rows**, matching an independent official `count(*)` response of **295,002** and the source metadata's CAMIS count. The request limit was 2,000,000, above the full dataset size; this is not a first-N-row sample.
- `data/nyc_inspections.csv.gz` preserves **every source row** and the five required fields, including violation duplicates. It is a compressed CSV, readable directly by pandas. The uncompressed download is excluded from Git to avoid duplicate storage.
- `data/restaurants.csv` contains **31,360 unique restaurants**, **24,804 rated restaurants**, and **22,183 Grade A restaurants**. Borough counts: Manhattan 12,576; Brooklyn 8,021; Queens 7,005; Bronx 2,637; Staten Island 1,121.
- `data/download_receipt.json` records the actual URL and completeness check. `data/data_quality.json` records counts, exclusions, date bounds and the SHA-256 of the compressed source. `data/source_metadata.json` preserves the official metadata read for this initial snapshot.

The official source covers establishments active at its record date, including not-yet-inspected applicants. It is not an all-time census or a list of restaurants guaranteed to be open today. Source documentation describes a rolling inspection window, but this snapshot contains some older records (earliest parsed date: August 10, 2007); this prototype does not silently impose a three-year cutoff. Latest observed inspection: November 4, 2026. Download date and inspection date are different concepts.

## Actual cleaning rules

`prepare_data.py` does the following in order:

1. Read CAMIS as text, trim surrounding whitespace, and normalize blank cells to missing. Keep only the five required fields. No fuzzy grouping of cuisine names is performed.
2. Parse inspection dates. Missing/unparseable dates, `1900-01-01` (the official not-yet-inspected marker), and dates after the download day cannot establish a latest graded inspection. Their restaurants can still count. **3,998 source rows** have invalid/placeholder dates under this rule.
3. Normalize borough names to the five boroughs. For each CAMIS, choose its most recent nonmissing valid borough and cuisine **independently**. This allows an older valid field to fill a missing field in a newer record. Same-date conflicting attributes use alphabetical order for deterministic results.
4. Drop missing CAMIS rows (**0** in this snapshot). Exclude restaurants with no valid five-borough value anywhere (**103**). Preserve restaurants with no known cuisine as **Unknown** (**3,922**), including them in all relevant count/share denominators. Unknown is missing classification, not a cuisine type.
5. Build one restaurant row per CAMIS. Repeated violations have no weight; projecting and deduplicating the five fields leaves **91,738 distinct required-field records** before the restaurant-level collapse.
6. Separately consider only A/B/C rows with a valid inspection date. For each CAMIS, take the **latest such inspection date**, even if a newer ungraded inspection exists. If conflicting A/B/C grades occur on that same latest day, choose the worse grade (C > B > A) and report the conflict count. There are **0 latest-day grade conflicts** in this snapshot.
7. Left-join that grade into the restaurant table, validating a one-to-one join and unique CAMIS. Unrated restaurants remain in the output. Save the selected graded inspection date separately from the restaurant's latest inspection date.

Grade is attached to the restaurant's latest valid borough/cuisine information. The older graded inspection need not have the same historical cuisine or borough; this is a snapshot of current recorded restaurant attributes with the latest available valid grade, not a longitudinal analysis.

## Metrics and chart scope

| Metric | Formula |
| --- | --- |
| Restaurant count | Number of unique CAMIS in the selected scope |
| Cuisine share | Cuisine's unique restaurants in one borough / **all** restaurants in that borough |
| Grade A percentage | Restaurants with latest valid grade A / restaurants with latest valid grade A, B or C |

**Why there is no duplicate restaurant counting:** every chart loads the one-row-per-CAMIS table, not the violation-level source table. The join is checked as one-to-one.

**Grade A denominator:** only A/B/C-rated restaurants. Missing grades, N, Z, P and other values never become non-A observations. A zero graded denominator means **no data**, not 0%.

- **Scatter / RQ3:** X = restaurant count; Y = Grade A percentage; one point per cuisine. All cuisines with at least one valid grade are included. There is no extra minimum sample cutoff. Fewer than 10 graded restaurants use hollow markers; hover gives cuisine, total count, graded count and Grade A %. Cuisines with zero rated restaurants are not plotted on a numeric percentage axis; a note reports them, and counts still include them. Small samples can show extreme percentages; the chart does not imply statistical significance or causation.
- **Bar / RQ1:** descending count, Top 10 in the selected borough. If a heatmap selection falls outside that Top 10, append that cuisine, preserve descending order, and change the title to “Top 10 + selected cuisine.” Orange fill and a `◀` text marker identify it. Ties are alphabetical.
- **Heatmap / RQ2:** rows = five boroughs, columns = citywide Top 10 cuisine categories (including Unknown where ranked). Purple intensity represents borough share. Top 10 selection does **not** reduce any denominator. Hover gives full names, count, share and total borough population. The matrix and color scale stay citywide while the other views filter, so it remains a stable comparison and selection control. Zero-count combinations are real zero shares when the borough has restaurants; missing borough denominators are no data.

## Interactions and demonstration

Color encodes selection in scatter/bar: saturated blue is the comparison set; bright orange with a dark outline identifies the selected cuisine. The same cuisine is highlighted consistently across both views. Cuisine identity is supplied by axis labels, hover and the selected point label rather than 90 different colors. Heatmap color has a separate quantitative role: a high-contrast, light-to-dark purple scale represents increasing borough share.

1. Start at **All NYC · All cuisines**.
2. Change **Borough**: scatter, bar and summary counts recompute. A manual borough change clears cuisine highlighting.
3. Click **Brooklyn × Chinese** on the heatmap. The dropdown changes to Brooklyn, both other charts recompute, and Chinese is highlighted with a labeled diamond in scatter and a marked bar. The selection reads **Brooklyn · Chinese**. A selection highlights a cuisine; it does not filter out the other cuisines.
4. Hover over each chart for exact values and denominator context.
5. Click **Reset** to return to All NYC and clear the cuisine. Clicking the same cell again works.

Below 900 px, chart panels stack vertically. On very narrow screens, the heatmap scrolls horizontally within its panel to preserve all 10 readable columns. Mouse/touch interaction with heatmap cells is the prototype selection mechanism; keyboard-only cell navigation is not implemented. Borough selection and Reset are keyboard accessible.

## Rebuild or refresh data

Rebuild the included snapshot without network access:

```sh
python prepare_data.py
```

Download a new full five-field snapshot and clean it:

```sh
python prepare_data.py --download
```

The downloader retries transient network errors and verifies row counts before and after download. It rejects incomplete/changing downloads and datasets that reach its request limit instead of silently truncating. A successful refresh updates the CSVs, receipt and audit; restart the app afterwards. Source metadata JSON is the preserved initial documentation, not a promise of refresh-time metadata.

For a complete CSV exported manually from the official portal, use its actual download date:

```sh
python prepare_data.py --input data/your_download.csv --download-date YYYY-MM-DD
```

This accepts portal uppercase labels or API field names. A manual import does not inherit the previous snapshot's completeness claim. The script prints source row count, columns, the first five rows and the cleaning audit. Do not use a truncated preview export.

## Validation

Run the analytical and boundary-case tests:

```sh
python -m unittest -v
```

Eight tests cover duplicate violations, independent latest grades, missing attributes, invalid dates, conflict handling, zero graded denominators, empty plots, five-borough reconciliations, every heatmap cell's full-population denominator, independent raw-row grade reconstruction, outside-Top-10 selection, Reset state and Dash HTTP routes.

Optional real-browser check (app running, Google Chrome installed):

```sh
pip install playwright==1.64.1
python check_browser.py
```

This checks rendered charts, all five borough selections, actual heatmap clicks, both highlights, hover text, Reset, selecting the same cell again, reload and narrow layout. It recreates the two screenshots. Snapshot counts in this browser regression script refer to the included November 9 dataset and must be updated intentionally after a data refresh.

## Submission materials

- [Default view: all three charts](screenshots/01-default.png)
- [Linked view: Brooklyn · Chinese](screenshots/02-brooklyn-chinese.png)
- [Feedback log template](feedback_log.md): intentionally not populated with invented feedback; fill it after the classroom demo.

The 2–3 page usability report and one-page reflection belong to the final stage and are not claimed as completed here.

## Code map and AI assistance

- `prepare_data.py`: `read_raw` standardizes fields; `clean_restaurants` creates attributes and latest-grade tables separately; `main` writes the auditable snapshot.
- `app.py`: `cuisine_summary` calculates counts and ratios; three figure functions draw plots; `select_state` handles selection rules; one Dash callback updates controls and dependent views together.
- `assets/style.css`: Option B layout, readable typography and responsive behavior.
- `test_dashboard.py`: data logic and boundary-case tests. `check_browser.py`: real-browser interactions and screenshots.

**AI assistance actually used:** OpenAI Codex generated the initial Python/CSS implementation, downloaded and inspected the official data, proposed and documented cleaning choices, wrote and executed automated checks, inspected browser screenshots, fixed chart-container overlap, and drafted this README and the empty feedback template. The dataset is real NYC Open Data; it is not AI-generated. No classroom feedback or user-study outcome has been invented. The student should review the code and be able to explain the unique-CAMIS collapse, separate latest-grade lookup, rate denominators, and callback state before submitting. AI testing is not classroom usability feedback.
