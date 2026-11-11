# A Taste of NYC

Python + Plotly Dash prototype for the NYC restaurant inspection visualization project.

**[Open the public dashboard](https://april-48.github.io/A-Teste-of-NYU/)** — no installation or local server required. This interactive edition uses the November 9, 2026 data snapshot; updates require rebuilding and publishing.

The complete application, included data snapshot, screenshots, and setup instructions are in **[a-taste-of-nyc/README.md](a-taste-of-nyc/README.md)**.

```sh
cd a-taste-of-nyc
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

Open **http://127.0.0.1:8050** while the server is running. This is a local Python application; GitHub Pages does not run the Dash server.
