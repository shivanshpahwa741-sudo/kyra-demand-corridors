#!/usr/bin/env python3
"""Inline Leaflet CSS + marker PNGs into kyra-demand-corridors.html → index.html."""
import urllib.request, base64, shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "pipeline" / "kyra-demand-corridors.html"
DST = ROOT / "index.html"

html = SRC.read_text()
# Inline Leaflet CSS
leaflet_css_url = "https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"
css = urllib.request.urlopen(leaflet_css_url, timeout=10).read().decode()
html = html.replace(
    '<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>',
    f"<style>{css}</style>",
)
# Inline marker PNGs
for name in ["marker-icon.png", "marker-icon-2x.png", "marker-shadow.png"]:
    data = urllib.request.urlopen(
        f"https://unpkg.com/leaflet@1.9.4/dist/images/{name}", timeout=10
    ).read()
    html = html.replace(
        f"url(images/{name})",
        f"url(data:image/png;base64,{base64.b64encode(data).decode()})",
    )
DST.write_text(html)
print(f"Wrote {DST} ({len(html)} B)")
