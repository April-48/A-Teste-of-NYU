"""Download a full NYC inspection snapshot and produce one row per CAMIS."""
from __future__ import annotations

import argparse
import hashlib
import json
import time
from datetime import datetime
from pathlib import Path
from urllib.request import urlopen
from zoneinfo import ZoneInfo

import pandas as pd

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
SOURCE_URL = "https://data.cityofnewyork.us/d/43nn-pn8j"
API = "https://data.cityofnewyork.us/resource/43nn-pn8j"
DOWNLOAD_URL = API + ".csv?%24select=camis%2Cboro%2Ccuisine_description%2Cinspection_date%2Cgrade&%24limit=2000000"
COUNT_URL = API + ".json?%24select=count%28%2A%29"
FIELDS = ["CAMIS", "BORO", "CUISINE DESCRIPTION", "INSPECTION DATE", "GRADE"]
BOROUGHS = ["Bronx", "Brooklyn", "Manhattan", "Queens", "Staten Island"]


def read_raw(path: Path) -> pd.DataFrame:
    """Accept either the portal's labels or Socrata API field names."""
    aliases = {c.lower().replace(" ", "_"): c for c in FIELDS}
    frame = pd.read_csv(path, dtype="string", keep_default_na=False,
                        usecols=lambda c: c in FIELDS or c in aliases)
    frame = frame.rename(columns=aliases)
    missing = set(FIELDS) - set(frame.columns)
    if missing:
        raise ValueError(f"Missing required columns: {sorted(missing)}")
    return frame[FIELDS]


def clean_restaurants(raw: pd.DataFrame, as_of: str) -> tuple[pd.DataFrame, dict]:
    """Attributes and grades have separate latest-record rules, then a 1:1 join."""
    df = raw[FIELDS].copy()
    for col in FIELDS:
        df[col] = df[col].astype("string").str.strip().replace("", pd.NA)
    missing_id = int(df.CAMIS.isna().sum())
    df = df.dropna(subset=["CAMIS"])
    df["BORO"] = df.BORO.str.casefold().map({b.casefold(): b for b in BOROUGHS})
    df["GRADE"] = df.GRADE.str.upper()
    dates = pd.to_datetime(df["INSPECTION DATE"], errors="coerce", format="mixed")
    invalid_date = dates.isna() | (dates <= pd.Timestamp("1900-01-01")) | (dates > pd.Timestamp(as_of))
    df["inspection_date"] = dates.mask(invalid_date)
    # Exact violation duplicates must never influence the chosen attributes.
    df = df.drop_duplicates()
    # Same-date conflicting attributes use alphabetical order as a stable tie-break.
    ordered = df.sort_values(["CAMIS", "inspection_date", "BORO", "CUISINE DESCRIPTION"],
                             na_position="first", kind="stable")
    ids = pd.Index(sorted(df.CAMIS.unique()), name="CAMIS")
    restaurants = pd.DataFrame(index=ids)
    for source, target in [("BORO", "borough"), ("CUISINE DESCRIPTION", "cuisine")]:
        valid = ordered.dropna(subset=[source]).drop_duplicates("CAMIS", keep="last")
        restaurants[target] = valid.set_index("CAMIS")[source]
    restaurants["latest_inspection_date"] = df.groupby("CAMIS").inspection_date.max()
    excluded_borough = int(restaurants.borough.isna().sum())
    restaurants = restaurants.dropna(subset=["borough"])
    unknown_cuisine = int(restaurants.cuisine.isna().sum())
    restaurants["cuisine"] = restaurants.cuisine.fillna("Unknown")

    graded = df[df.GRADE.isin(["A", "B", "C"]) & df.inspection_date.notna()].copy()
    latest_dates = graded.groupby("CAMIS").inspection_date.transform("max")
    latest = graded[graded.inspection_date.eq(latest_dates)].copy()
    conflicts = int((latest.groupby("CAMIS").GRADE.nunique() > 1).sum())
    # In the rare same-day A/B/C conflict, retain the worse grade (C > B > A).
    latest = latest.sort_values(["CAMIS", "GRADE"]).drop_duplicates("CAMIS", keep="last")
    grades = latest.set_index("CAMIS")[["GRADE", "inspection_date"]].rename(
        columns={"GRADE": "grade", "inspection_date": "graded_inspection_date"})
    restaurants = restaurants.join(grades, how="left", validate="one_to_one").reset_index()
    assert restaurants.CAMIS.is_unique
    audit = {
        "raw_rows": len(raw), "rows_missing_camis": missing_id,
        "invalid_or_placeholder_date_rows": int(invalid_date.sum()),
        "distinct_required_field_rows": len(df),
        "restaurants_excluded_no_valid_borough": excluded_borough,
        "restaurants_unknown_cuisine": unknown_cuisine,
        "latest_date_grade_conflicts": conflicts,
        "restaurants": len(restaurants),
        "rated_restaurants": int(restaurants.grade.isin(["A", "B", "C"]).sum()),
        "grade_a_restaurants": int(restaurants.grade.eq("A").sum()),
        "borough_counts": {str(k): int(v) for k, v in restaurants.borough.value_counts().items()},
        "cuisines": int(restaurants.cuisine.nunique()),
        "inspection_date_min": str(df.inspection_date.min()),
        "inspection_date_max": str(df.inspection_date.max()),
    }
    return restaurants, audit


def download() -> Path:
    DATA.mkdir(exist_ok=True)
    target = DATA / "nyc_inspections.csv"
    temporary = target.with_suffix(".csv.part")
    print("Downloading all source rows, projecting the five required fields…", flush=True)
    def fetch(url):
        for attempt in range(3):
            try:
                with urlopen(url, timeout=300) as response:
                    return response.read()
            except OSError:
                if attempt == 2:
                    raise
                time.sleep(2 ** attempt)
    expected = int(json.loads(fetch(COUNT_URL))[0]["count"])
    if expected >= 2_000_000:
        raise ValueError("Dataset exceeds this downloader's limit. Use a complete portal CSV export.")
    temporary.write_bytes(fetch(DOWNLOAD_URL))
    raw = read_raw(temporary)
    after = int(json.loads(fetch(COUNT_URL))[0]["count"])
    if len(raw) != expected or after != expected:
        raise ValueError("Source changed or download is incomplete; retry. Existing snapshot is unchanged.")
    temporary.replace(target)
    stamp = datetime.now(ZoneInfo("America/New_York")).isoformat()
    (DATA / "download_receipt.json").write_text(json.dumps({
        "downloaded_at": stamp, "source_url": SOURCE_URL, "download_url": DOWNLOAD_URL,
        "sha256_full_csv": hashlib.sha256(target.read_bytes()).hexdigest(),
        "official_row_count": expected, "downloaded_rows": len(raw),
        "completeness_verified": True, "count_url": COUNT_URL,
    }, indent=2) + "\n")
    return target


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--download", action="store_true", help="Fetch a new full official snapshot")
    parser.add_argument("--input", type=Path, help="CSV/CSV.gz to clean; use --download for a fresh snapshot")
    parser.add_argument("--download-date", help="Actual YYYY-MM-DD download date for a manually downloaded CSV")
    args = parser.parse_args()
    DATA.mkdir(exist_ok=True)
    path = download() if args.download else args.input
    if path is None:
        path = DATA / "nyc_inspections.csv.gz"
        if not path.exists():
            path = DATA / "nyc_inspections.csv"
    if not path.exists():
        parser.error("No source CSV found. Run: python prepare_data.py --download")
    receipt_path = DATA / "download_receipt.json"
    receipt = json.loads(receipt_path.read_text()) if receipt_path.exists() else {}
    if args.input and not args.download_date:
        parser.error("A custom --input requires its actual --download-date YYYY-MM-DD.")
    date = args.download_date or receipt.get("downloaded_at", "")[:10]
    if not date:
        parser.error("Supply --download-date YYYY-MM-DD for this manually downloaded file.")
    raw = read_raw(path)
    print(f"Rows: {len(raw):,}\nColumns: {list(raw.columns)}\n{raw.head().to_string(index=False)}")
    restaurants, audit = clean_restaurants(raw, date)
    # Keep every source row, only projecting the five needed columns; gzip is Git-friendly.
    snapshot = DATA / "nyc_inspections.csv.gz"
    if path.resolve() != snapshot.resolve():
        raw.to_csv(snapshot, index=False, compression={"method": "gzip", "mtime": 0})
    restaurants.to_csv(DATA / "restaurants.csv", index=False, date_format="%Y-%m-%d")
    # A custom input is not automatically covered by another file's download receipt.
    if args.input:
        receipt = {"downloaded_at": date, "input_file": path.name,
                   "input_sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
        receipt_path.write_text(json.dumps(receipt, indent=2) + "\n")
    metadata = {**receipt, "source_url": SOURCE_URL, "download_date": date,
                "prepared_at": datetime.now(ZoneInfo("America/New_York")).isoformat(),
                "source_snapshot": snapshot.name,
                "sha256_snapshot": hashlib.sha256(snapshot.read_bytes()).hexdigest(), **audit}
    (DATA / "data_quality.json").write_text(json.dumps(metadata, indent=2) + "\n")
    print(json.dumps(audit, indent=2))


if __name__ == "__main__":
    main()
