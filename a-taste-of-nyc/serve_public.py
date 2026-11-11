"""Preview an exported site with its required JSON response types.

Usage: python serve_public.py public-dist [port]
Production static hosting must honor the export's _headers file.
"""
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import sys


class ExportHandler(SimpleHTTPRequestHandler):
    def guess_type(self, path):
        if path.endswith(("/_dash-layout", "/_dash-dependencies")):
            return "application/json"
        return super().guess_type(path)


if __name__ == "__main__":
    directory = Path(sys.argv[1]).resolve()
    port = int(sys.argv[2]) if len(sys.argv) > 2 else 8060
    print(f"Public export preview: http://127.0.0.1:{port}", flush=True)
    ThreadingHTTPServer(("127.0.0.1", port), partial(ExportHandler, directory=str(directory))).serve_forever()
