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
4. Drop missing CAMIS rows (**0** in this snapshot). Exclude restaurants with no valid five-borough value anywhere (**103**). Preserve restaurants with no known cuisine as **Unknown** (**3,922**), including them in all relevant count/share denominators. The UI calls this **Cuisine not recorded**, and excludes it from the cuisine comparisons. `Unknown` remains only as the existing internal missing-value label in the cleaned CSV.
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

- **Scatter / RQ3:** X = restaurant count (linear); Y = Grade A percentage; one point per recorded cuisine with at least one valid grade. The dashed line is the pooled Grade A rate for the selected scope, including every validly graded restaurant. Teal triangles = at or above that rate; warm orange squares = below it. The dashed line has an explicit legend and its percentage is labeled at the right endpoint. The selected cuisine keeps its comparison color, with a black outline and label. Markers are smaller and semi-transparent; fewer than 10 graded restaurants remain hollow. The optional **At least 10 graded restaurants** checkbox is off by default. When enabled, it hides cuisines with fewer than 10 valid grades only from scatter, displays the number hidden, and leaves all totals and the pooled benchmark unchanged. A selected cuisine hidden by this filter is explicitly named beside the checkbox. Zero-rated cuisines are not plotted on a numeric percentage axis. Above/below overall is descriptive, not statistical significance or causation.
- **Bar / RQ1:** descending restaurant count, Top 10 recorded cuisines in the selected borough. If any chart selection falls outside that Top 10, append the selected cuisine, disclose this in the title, and show its actual rank among recorded cuisines. Ordinary bars are gray-blue; a dark desaturated teal bar and bold cuisine label identify selection. Counts remain at bar ends; the former arrow and redundant Cuisine axis title are removed. Ties are alphabetical.
- **Heatmap / RQ2:** five boroughs × citywide Top 10 recorded cuisines. Purple intensity represents borough share, and every cell displays its percentage. Text switches to white on darker cells. All five cells in the selected cuisine column have thin outlines; the active borough–cuisine cell has a heavier outline and the active borough label is bold. A cuisine selected from scatter/bar outside the NYC Top 10 is appended as an eleventh column. All five boroughs and the citywide color scale remain fixed across selections. The nearby subtitle explicitly says “Share within each borough · All five boroughs.” All borough restaurants, including Cuisine not recorded, remain in the denominator. Zero-count combinations remain 0%; zero denominators are no data.

## Missing-cuisine audit

The November 9 snapshot was checked directly against every available source row for each CAMIS classified as Unknown:

- **3,922 unique restaurants** have no recorded cuisine, including **992 in Brooklyn**.
- These IDs have **4,000 source rows**. **Zero** of those restaurant IDs have any nonblank cuisine in any available inspection record. The missing values were not introduced by mapping or the grade join, and there is no usable older cuisine to recover.
- None has a valid A/B/C grade. **3,920 source rows** carry the source's `1900-01-01` not-yet-inspected marker; this count is rows, not restaurants.
- They remain in total restaurant counts and heatmap denominators, but are excluded from cuisine comparisons and Top 10 selection. A visible note states their count for the current borough and the denominator policy. The cleaned data is retained intact.

The saved audit is [data/cuisine_missingness_audit.json](data/cuisine_missingness_audit.json). `test_missing_cuisine_really_missing_in_all_source_records` repeats the key raw-source check. Brooklyn's reference rate is **5,707 Grade A / 6,325 A/B/C-rated = 90.229249…%**, displayed as **90.2%**. It is not the unweighted average of cuisine rates.

## Visual channel table

| View | Mark / channel | Meaning |
| --- | --- | --- |
| Scatter / RQ3 | One point | One recorded cuisine with at least one valid A/B/C grade |
| Scatter / RQ3 | Horizontal position | Unique restaurant count; linear X axis |
| Scatter / RQ3 | Vertical position | Latest valid Grade A percentage |
| Scatter / RQ3 | Teal triangle / warm orange square | At or above / below the selected scope's pooled Grade A rate |
| Scatter / RQ3 | Dashed horizontal line | All Grade A restaurants divided by all A/B/C-rated restaurants in scope |
| Scatter / RQ3 | Hollow triangle or square | Fewer than 10 graded restaurants |
| Scatter / RQ3 | Black outline + text label | Selected cuisine; its comparison color and shape are preserved |
| Bar / RQ1 | Length and sorted position | Unique restaurant count, descending |
| Bar / RQ1 | Gray-blue / dark teal + bold label | Background comparison / selected cuisine |
| Heatmap / RQ2 | Row / column | Borough / citywide Top 10 recorded cuisines, plus selected cuisine if needed |
| Heatmap / RQ2 | Sequential purple intensity + cell text | Cuisine share among **all** restaurants in that borough |
| Heatmap / RQ2 | Thin column outlines / heavy cell outline / bold row label | Selected cuisine across boroughs / selected borough–cuisine / active borough |

These refinements retain Option B and the original chart types and axes. The added reference line and binary comparison colors strengthen RQ3. No logarithmic axis or arbitrary cuisine palette was introduced. Only the selected scatter point is labeled to limit clutter. Display numbers 01–03 express reading order; the original research-question mapping remains RQ3 / RQ1 / RQ2.

The readability revision uses a 42 px desktop page title, 22–24 px chart titles, 14 px scope subtitles and 13–15 px chart labels. The right column receives more width, short chart titles are separated from scope subtitles, and heatmap labels use a consistent 40° angle instead of shrinking type. Dark text, stronger teal/orange marks and subtle section rules separate the three views without card borders. Data and selection behavior are unchanged.

## Interactions and demonstration

1. Start at **All NYC · All cuisines**. Other cuisines always remain as comparison context when selecting one.
2. Click **Chinese** in the bar: scatter labels/outlines Chinese, and heatmap outlines its entire column. Click **American** in scatter: the bar and heatmap switch to American.
3. Click **Brooklyn × Chinese** on the heatmap. The dropdown changes to Brooklyn; bar and scatter recompute, and all three charts highlight Chinese. The selected heatmap cell is outlined more heavily than the other four cells in that column.
4. Click **Brooklyn × Italian**: Italian is appended to Brooklyn's bar with **Selected cuisine · Rank 11**. Click **Caribbean** in that bar: heatmap adds Caribbean as an extra column because it is outside the NYC Top 10.
5. Enable **At least 10 graded restaurants**. Brooklyn hides **24 cuisines** from scatter; the other charts, counts and overall reference remain unchanged. The control is off by default. Zero-rated cuisines cannot appear on the percentage axis and are reported separately.
6. Hover over each chart. Scatter shows cuisine, borough, total restaurants, A/B/C-rated count, Grade A count and Grade A percentage. Bar shows cuisine, borough, count, share of all restaurants and rank. Heatmap shows borough, cuisine, count, share and its full-borough denominator.
7. Click **Reset** to return to All NYC, clear the cuisine and turn off the sample filter. Clicking the same mark again works. Manual borough changes clear cuisine selection and retain the sample-filter setting.

The three chart click paths, the Italian rank-11 case, the appended Caribbean column, sample filtering, Reset and repeated selection were exercised in the running browser on November 9, 2026. The two screenshots were refreshed after these changes; screenshots supplement the interactive demonstration rather than proving it alone.

Below 1150 px, chart panels stack vertically. When the heatmap cannot fit readable columns, it scrolls horizontally within its panel; the narrow-screen subtitle explains this. Mouse/touch chart marks initiate selection; keyboard-only chart-mark navigation is not implemented. Borough selection, the sample checkbox and Reset are keyboard accessible.

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

Thirteen tests cover duplicate violations, independent latest grades, missing attributes, invalid dates, conflict handling, zero graded denominators, empty plots, five-borough reconciliations, every heatmap cell's full-population denominator, independent raw-row grade reconstruction, outside-Top-10 selection, Reset state and Dash HTTP routes. Added checks verify source missingness, pooled benchmark weighting, preservation of comparison colors on selection, heatmap values/outlines, and a fixed citywide color scale. Callback HTTP tests exercise all three click inputs, sample filtering without changing the benchmark, out-of-Top-10 additions, tooltip denominators and Reset.

Optional real-browser check (app running, Google Chrome installed):

```sh
pip install playwright==1.64.1
python check_browser.py
```

This checks rendered charts, all five borough selections, clicks in all three charts, linked highlights, hover text, the sample filter, Reset, selecting the same cell again, reload and narrow layout. It recreates the two screenshots. Snapshot counts in this browser regression script refer to the included November 9 dataset and must be updated intentionally after a data refresh.

## Submission materials

- [Default view: all three charts](screenshots/01-default.jpg)
- [Linked view: Brooklyn · Chinese](screenshots/02-brooklyn-chinese.jpg)
- [Feedback log template](feedback_log.md): intentionally not populated with invented feedback; fill it after the classroom demo.

The 2–3 page usability report and one-page reflection belong to the final stage and are not claimed as completed here.

## Code map and AI assistance

- `prepare_data.py`: `read_raw` standardizes fields; `clean_restaurants` creates attributes and latest-grade tables separately; `main` writes the auditable snapshot.
- `app.py`: `cuisine_summary` calculates counts and ratios; three figure functions draw plots; `select_state` handles selection rules; one Dash callback updates controls and dependent views together.
- `assets/style.css`: Option B layout, readable typography and responsive behavior.
- `test_dashboard.py`: data logic and boundary-case tests. `check_browser.py`: real-browser interactions and screenshots.

**AI assistance actually used:** OpenAI Codex generated the initial Python/CSS implementation, downloaded and inspected the official data, proposed and documented cleaning choices, wrote and executed automated checks, inspected browser screenshots, fixed chart-container overlap, audited missing cuisine against all source records, implemented the user-requested benchmark color encoding, visual hierarchy changes, three-way linked selection and sample filter, and drafted this README and the empty feedback template. The dataset is real NYC Open Data; it is not AI-generated. No classroom feedback or user-study outcome has been invented. The student should review the code and be able to explain the unique-CAMIS collapse, separate latest-grade lookup, rate denominators, and callback state before submitting. AI testing is not classroom usability feedback.
