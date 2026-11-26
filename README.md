# A Taste of NYC

**[Open the interactive dashboard](https://april-48.github.io/A-Teste-of-NYU/)**

Explore New York City's cuisines, restaurant counts, inspection Grade A rates and cuisine shares across the five boroughs. The public dashboard requires no installation or local Python server.

The three linked views keep the original arrangement: a scatter plot on the left, a restaurant ranking at upper right, and a switchable heatmap or geographic map at lower right. Cuisine selection is shared across the views. Filters, informative tooltips and an expanded view are available for each chart.

The public edition uses the NYC DOHMH snapshot downloaded on November 9, 2026. Grade A describes inspection results, not taste or food quality. Changes to the data require a new export and publication.

## Run locally

```sh
cd a-taste-of-nyc
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

Open http://127.0.0.1:8050 while the local server is running.

## Source and publication

The application and data documentation are in [a-taste-of-nyc/README.md](a-taste-of-nyc/README.md). GitHub Actions builds the fixed-snapshot dashboard, verifies its exported calculations against the Python callbacks and deploys it to GitHub Pages after changes to the application on `main`.
