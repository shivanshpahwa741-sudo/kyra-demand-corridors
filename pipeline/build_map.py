#!/usr/bin/env python3
"""Build the demand corridors HTML from locality-level data with recency weighting."""
import json, os, re, math
from datetime import datetime
from collections import defaultdict, Counter

SCRATCH = os.path.dirname(os.path.abspath(__file__))
RIDES = os.path.join(SCRATCH, 'rides_enriched.json')
LOCS = os.path.join(SCRATCH, 'localities.json')
ROUTES = os.path.join(SCRATCH, 'locality_routes.json')
OUT = os.path.join(SCRATCH, 'kyra-demand-corridors.html')

HALF_LIFE_DAYS = 21

def main():
    rides = json.load(open(RIDES))
    locs = json.load(open(LOCS))
    routes = json.load(open(ROUTES))

    parsed = []
    for r in rides:
        w = r.get('when')
        when = datetime.fromisoformat(w) if w else None
        parsed.append({**r, 'when_dt': when})

    valid_times = [r['when_dt'] for r in parsed if r['when_dt']]
    now = max(valid_times) if valid_times else datetime.now()
    earliest = min(valid_times) if valid_times else datetime.now()
    span_days = (now - earliest).days
    print(f'Time span: {span_days} days ({earliest.date()} → {now.date()})')

    def recency_weight(dt):
        if not dt: return 0.2
        days_old = (now - dt).days
        return math.exp(-days_old / HALF_LIFE_DAYS)

    # Dedup retries: (rider, from_loc, to_loc) within 60-min rolling window → single
    parsed.sort(key=lambda r: r['when_dt'] or datetime.min)
    last_seen = {}
    deduped = []
    dropped_retries = 0
    for r in parsed:
        dt = r['when_dt']
        rider = (r.get('rider') or '').strip().lower()
        key = (rider, r.get('from_loc'), r.get('to_loc'))
        if dt and rider and key in last_seen and (dt - last_seen[key]).total_seconds() <= 3600:
            dropped_retries += 1
            last_seen[key] = dt
            continue
        if dt: last_seen[key] = dt
        deduped.append(r)
    print(f'Dropped {dropped_retries} retries within 60 min → {len(deduped)} unique booking intents')
    parsed = deduped

    # Filter team/excluded names at ride level
    import re as _re
    parsed = [r for r in parsed if not _re.match(r'^(Divyashri|Aflah|Sharmila)\b', (r.get('rider') or '').strip(), _re.I)]
    print(f'After filter: {len(parsed)}')

    corridors = defaultdict(lambda: {'count': 0, 'recent_count': 0, 'weighted': 0.0, 'last': None})
    locality_pickup = Counter()
    locality_drop = Counter()
    locality_pickup_recent = Counter()
    locality_drop_recent = Counter()
    RECENT_CUTOFF_DAYS = 30

    for r in parsed:
        f, t = r['from_loc'], r['to_loc']
        if not f or not t or f == t: continue
        dt = r['when_dt']
        w = recency_weight(dt)
        is_recent = dt and (now - dt).days <= RECENT_CUTOFF_DAYS
        locality_pickup[f] += 1
        locality_drop[t] += 1
        if is_recent:
            locality_pickup_recent[f] += 1
            locality_drop_recent[t] += 1
        c = corridors[(f, t)]
        c['count'] += 1
        c['weighted'] += w
        if is_recent: c['recent_count'] += 1
        if not c['last'] or (dt and dt > c['last']):
            c['last'] = dt

    final = []
    for (f, t), c in corridors.items():
        key = f'{f}||{t}'
        rt = routes.get(key)
        if not rt: continue
        g1 = locs.get(f); g2 = locs.get(t)
        if not g1 or not g2: continue
        final.append({
            'f': f, 't': t,
            'count': c['count'], 'recent': c['recent_count'],
            'weighted': round(c['weighted'], 3),
            'last': c['last'].isoformat() if c['last'] else None,
            'geom': rt['geom'],
            'dist_km': round(rt['distance_m']/1000, 1),
            'dur_min': round(rt['duration_s']/60),
        })

    final.sort(key=lambda x: -x['weighted'])
    total_mapped = sum(c['count'] for c in final)
    total_rides = len(rides)

    def named(c):
        return not (c['f'].startswith('PIN ') or c['t'].startswith('PIN '))
    named_only = [c for c in final if named(c)]
    top_recency = named_only[:10]
    top_volume = sorted(named_only, key=lambda x: -x['count'])[:10]
    top_last30 = sorted([c for c in named_only if c['recent'] > 0], key=lambda x: -x['recent'])[:10]

    locality_markers = []
    for loc, g in locs.items():
        if not g: continue
        pick = locality_pickup.get(loc, 0)
        drop = locality_drop.get(loc, 0)
        if pick + drop == 0: continue
        locality_markers.append({
            'name': loc, 'lat': g['lat'], 'lon': g['lon'],
            'pickups': pick, 'dropoffs': drop,
            'pickups_recent': locality_pickup_recent.get(loc, 0),
            'dropoffs_recent': locality_drop_recent.get(loc, 0),
        })

    payload = {
        'corridors': [{
            'f': c['f'], 't': c['t'], 'c': c['count'], 'r': c['recent'],
            'w': c['weighted'], 'g': c['geom'], 'd': c['dist_km'], 'm': c['dur_min'],
        } for c in final],
        'localities': locality_markers,
        'total_rides': total_rides,
        'total_unique': len(parsed),
        'total_mapped': total_mapped,
        'unique_corridors': len(final),
        'top_recency': top_recency,
        'top_volume': top_volume,
        'top_last30': top_last30,
        'now': now.isoformat(),
        'earliest': earliest.isoformat(),
        'span_days': span_days,
        'half_life_days': HALF_LIFE_DAYS,
    }

    data_json = json.dumps(payload, default=str, separators=(',', ':'))
    html = HTML_TEMPLATE.replace('__DATA__', data_json)
    with open(OUT, 'w') as f: f.write(html)
    print(f'Wrote {OUT}')
    print(f'  Corridors: {len(final)}')
    print(f'  Rides mapped: {total_mapped}/{total_rides}')
    print(f'  Locality markers: {len(locality_markers)}')
    print(f'  Top by recency: {top_recency[0]["f"]} → {top_recency[0]["t"]} ({top_recency[0]["count"]} rides)' if top_recency else '  No top corridor')


HTML_TEMPLATE = r'''<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Kyra Demand Corridors</title>
<meta name="description" content="Bengaluru demand corridors for Kyra, ranked by recency of request.">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<style>
  :root {
    --bg: #0a0a0d;
    --panel: rgba(16, 16, 20, 0.88);
    --panel-border: rgba(255,255,255,0.08);
    --ink: #f5f3ea;
    --ink-soft: #c5c2b5;
    --muted: #7a7768;
    --accent: #ff3860;
    --hot: #ffcc33;
    --warm: #ff8833;
    --cool: #ff4d7a;
  }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  html, body { height: 100%; font-family: 'Inter', system-ui, sans-serif; background: var(--bg); color: var(--ink); overflow: hidden; -webkit-font-smoothing: antialiased; }
  #map { position: absolute; inset: 0; background: #0a0a0d; }
  .leaflet-container { background: #0a0a0d; font-family: 'Inter', system-ui, sans-serif; }

  .collapse-btn {
    background: transparent; border: none; cursor: pointer; padding: 4px 8px;
    color: var(--ink-soft); font-size: 14px; font-family: inherit; line-height: 1;
    border-radius: 6px; transition: background 0.15s, transform 0.2s;
  }
  .collapse-btn:hover { background: rgba(255,255,255,0.08); }
  .collapsed .collapse-btn { transform: rotate(180deg); }
  .collapsed .panel-body { display: none; }
  .collapsed .panel-head { margin-bottom: 0; padding-bottom: 0; border-bottom: none; }

  .masthead {
    position: absolute; top: 18px; left: 18px; z-index: 500;
    background: var(--panel); backdrop-filter: blur(14px);
    border: 1px solid var(--panel-border); border-radius: 12px;
    padding: 14px 18px; max-width: 360px;
    box-shadow: 0 10px 40px rgba(0,0,0,0.5);
  }
  .masthead .panel-head { display: flex; align-items: center; justify-content: space-between; gap: 10px; }
  .masthead .panel-body { margin-top: 8px; }
  .brand { font-size: 10px; font-weight: 700; letter-spacing: 3px; color: var(--accent); text-transform: uppercase; margin-bottom: 6px; }
  .title { font-size: 24px; font-weight: 700; letter-spacing: -0.3px; line-height: 1.15; margin-bottom: 6px; }
  .sub { font-size: 12.5px; color: var(--ink-soft); line-height: 1.45; }
  .sub b { color: var(--ink); }

  .stats-strip {
    position: absolute; top: 18px; right: 18px; z-index: 500;
    display: grid; grid-template-columns: repeat(4, auto); gap: 8px;
  }
  .stat-tile {
    background: var(--panel); backdrop-filter: blur(14px);
    border: 1px solid var(--panel-border); border-radius: 10px;
    padding: 12px 16px; min-width: 100px;
  }
  .stat-num { font-size: 22px; font-weight: 700; color: var(--ink); letter-spacing: -0.5px; line-height: 1; }
  .stat-num.hot { color: var(--hot); }
  .stat-cap { font-size: 9px; font-weight: 600; color: var(--muted); text-transform: uppercase; letter-spacing: 1.2px; margin-top: 7px; }

  .panel {
    position: absolute; bottom: 18px; left: 18px; z-index: 500;
    background: var(--panel); backdrop-filter: blur(14px);
    border: 1px solid var(--panel-border); border-radius: 12px;
    padding: 18px 20px; width: 380px;
    box-shadow: 0 10px 40px rgba(0,0,0,0.5);
  }
  .panel-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
  .panel-head h2 { font-size: 10px; font-weight: 700; letter-spacing: 2px; color: var(--accent); text-transform: uppercase; }
  .sort-tabs { display: flex; gap: 0; background: rgba(255,255,255,0.05); border-radius: 100px; padding: 3px; }
  .sort-tab { background: transparent; border: none; color: var(--muted); font-size: 9.5px; font-weight: 600; letter-spacing: 0.6px; text-transform: uppercase; padding: 5px 10px; border-radius: 100px; cursor: pointer; font-family: inherit; }
  .sort-tab.active { background: var(--accent); color: #fff; }

  .corridor-list { list-style: none; padding: 0; margin: 0; max-height: 400px; overflow-y: auto; }
  .corridor-list::-webkit-scrollbar { width: 6px; }
  .corridor-list::-webkit-scrollbar-thumb { background: rgba(255,255,255,0.1); border-radius: 3px; }
  .corridor-list li { padding: 10px 10px; border-bottom: 1px solid rgba(255,255,255,0.05); cursor: pointer; transition: background 0.15s; border-radius: 4px; }
  .corridor-list li:last-child { border-bottom: none; }
  .corridor-list li:hover { background: rgba(255,255,255,0.05); }
  .corridor-list .rank { display: inline-block; width: 20px; font-size: 10px; font-weight: 700; color: var(--accent); margin-right: 8px; }
  .corridor-list .route { font-size: 13px; color: var(--ink); line-height: 1.35; font-weight: 500; }
  .corridor-list .route .arrow { color: var(--muted); margin: 0 6px; font-weight: 400; }
  .corridor-list .meta { font-size: 10.5px; color: var(--muted); margin-top: 4px; margin-left: 28px; display: flex; gap: 10px; flex-wrap: wrap; }
  .corridor-list .count-pill { color: var(--hot); font-weight: 700; }
  .corridor-list .recent-pill { color: var(--accent); font-weight: 600; }
  .corridor-list .ago { color: var(--muted); }

  .legend {
    position: absolute; bottom: 18px; right: 18px; z-index: 500;
    background: var(--panel); backdrop-filter: blur(14px);
    border: 1px solid var(--panel-border); border-radius: 12px;
    padding: 14px 16px; width: 230px;
  }
  .legend h3 { font-size: 10px; font-weight: 700; letter-spacing: 2px; color: var(--accent); text-transform: uppercase; margin-bottom: 10px; }
  .legend-row { font-size: 11px; color: var(--ink-soft); display: flex; align-items: center; gap: 10px; margin-bottom: 6px; }
  .legend-swatch { width: 24px; height: 3px; border-radius: 2px; flex-shrink: 0; }
  .legend-note { font-size: 10px; color: var(--muted); margin-top: 10px; padding-top: 10px; border-top: 1px solid rgba(255,255,255,0.06); line-height: 1.45; }

  .toggles {
    position: absolute; top: 18px; left: 50%; transform: translateX(-50%); z-index: 500;
    background: var(--panel); backdrop-filter: blur(14px);
    border: 1px solid var(--panel-border); border-radius: 100px;
    padding: 4px; display: flex; gap: 2px;
  }
  .toggle-btn {
    background: transparent; border: none; color: var(--ink-soft);
    padding: 8px 18px; font-size: 11px; font-weight: 600; letter-spacing: 0.5px;
    cursor: pointer; border-radius: 100px; font-family: inherit;
  }
  .toggle-btn.active { background: var(--accent); color: #fff; }
  .toggle-btn:hover:not(.active) { background: rgba(255,255,255,0.06); }

  .footer-tag {
    position: absolute; bottom: 10px; left: 50%; transform: translateX(-50%); z-index: 400;
    font-size: 9.5px; color: var(--muted); letter-spacing: 2px; text-transform: uppercase; pointer-events: none;
  }

  .leaflet-control-attribution { background: rgba(13,13,16,0.75) !important; color: var(--muted) !important; font-size: 9px !important; padding: 2px 6px !important; }
  .leaflet-control-attribution a { color: var(--ink-soft) !important; }
  .leaflet-control-zoom a { background: var(--panel) !important; color: var(--ink) !important; border-color: var(--panel-border) !important; }
  .leaflet-popup-content-wrapper { background: var(--panel); color: var(--ink); border-radius: 8px; border: 1px solid var(--panel-border); }
  .leaflet-popup-content { font-size: 12px; line-height: 1.55; margin: 12px 14px; color: var(--ink); }
  .leaflet-popup-tip { background: rgba(16,16,20,0.95); }
  .popup-head { font-weight: 700; color: var(--hot); font-size: 13px; margin-bottom: 4px; }
  .popup-stat { color: var(--ink-soft); margin-top: 2px; }
  .popup-stat b { color: var(--ink); }

  .loc-label { pointer-events: none; }
  .loc-label span { color: #f5f0e0; font-weight: 600; letter-spacing: 0.1px; text-shadow: 0 0 4px #000, 0 0 7px #000, 0 1px 2px rgba(0,0,0,0.95); white-space: nowrap; font-family: 'Inter', sans-serif; transition: font-size 0.2s, opacity 0.25s; }

  @media (max-width: 760px) {
    .masthead { top: 10px; left: 10px; right: 10px; max-width: none; padding: 10px 14px; }
    .title { font-size: 15px; }
    .sub { font-size: 11px; line-height: 1.35; }
    .brand { font-size: 9px; letter-spacing: 2px; }
    .stats-strip { top: auto; bottom: 10px; right: 10px; left: 10px; grid-template-columns: repeat(4, 1fr); gap: 4px; }
    .stat-tile { padding: 8px 10px; min-width: 0; text-align: center; }
    .stat-num { font-size: 15px; }
    .stat-cap { font-size: 8px; letter-spacing: 0.8px; margin-top: 4px; }
    .toggles { top: 68px; padding: 3px; }
    .toggle-btn { padding: 6px 12px; font-size: 10px; }
    .panel { right: 10px; left: 10px; bottom: auto; top: 112px; width: auto; padding: 12px 14px; }
    .panel .corridor-list { max-height: 44vh; }
    .legend { display: none; }
    .footer-tag { display: none; }
    .leaflet-control-zoom { display: none; }
  }
  @media (max-width: 900px) and (min-width: 761px) {
    .masthead { max-width: 260px; padding: 14px 16px; }
    .title { font-size: 18px; }
    .sub { font-size: 11.5px; }
    .stat-num { font-size: 18px; }
    .panel { width: 320px; }
    .legend { display: none; }
  }
</style>
</head>
<body>
<div id="map"></div>

<div class="masthead" id="masthead">
  <div class="panel-head">
    <div>
      <div class="brand">KYRA · Demand corridors</div>
      <div class="title">Where women want to go in Bengaluru</div>
    </div>
    <button class="collapse-btn" data-target="masthead" aria-label="Collapse">⌃</button>
  </div>
  <div class="panel-body">
    <div class="sub">Every unique booking intent on the app, mapped on real roads and ranked by how <b>recent</b> the demand is. Brighter corridors are both busier and fresher. Retries within 60 min count once.</div>
  </div>
</div>

<div class="stats-strip">
  <div class="stat-tile"><div class="stat-num" id="stat-rides">—</div><div class="stat-cap">Requests mapped</div></div>
  <div class="stat-tile"><div class="stat-num" id="stat-corridors">—</div><div class="stat-cap">Unique corridors</div></div>
  <div class="stat-tile"><div class="stat-num hot" id="stat-top-count">—</div><div class="stat-cap">Top corridor</div></div>
  <div class="stat-tile"><div class="stat-num" id="stat-window">—</div><div class="stat-cap">Days of data</div></div>
</div>

<div class="toggles">
  <button class="toggle-btn active" data-view="corridors">Corridors</button>
  <button class="toggle-btn" data-view="pickups">Pickups</button>
  <button class="toggle-btn" data-view="dropoffs">Drop-offs</button>
</div>

<div class="panel" id="panel">
  <div class="panel-head">
    <h2>Top corridors</h2>
    <div style="display:flex; align-items:center; gap:8px;">
      <div class="sort-tabs">
        <button class="sort-tab active" data-sort="recency">Recency</button>
        <button class="sort-tab" data-sort="volume">Volume</button>
        <button class="sort-tab" data-sort="last30">Last 30 d</button>
      </div>
      <button class="collapse-btn" data-target="panel" aria-label="Collapse">⌃</button>
    </div>
  </div>
  <div class="panel-body">
    <ul class="corridor-list" id="top-list"></ul>
  </div>
</div>

<div class="legend" id="legend">
  <div class="panel-head" style="display:flex; justify-content:space-between; align-items:center; margin-bottom:10px;">
    <h3 style="margin:0;">Reading the map</h3>
    <button class="collapse-btn" data-target="legend" aria-label="Collapse">⌃</button>
  </div>
  <div class="panel-body">
    <div class="legend-row"><div class="legend-swatch" style="background: rgba(255,77,122,0.3); height: 1.5px;"></div>1 request</div>
    <div class="legend-row"><div class="legend-swatch" style="background: rgba(255,77,122,0.75); height: 3px;"></div>2–4 requests</div>
    <div class="legend-row"><div class="legend-swatch" style="background: rgba(255,136,51,0.9); height: 5px;"></div>5–9 requests</div>
    <div class="legend-row"><div class="legend-swatch" style="background: rgba(255,204,51,1); height: 7px;"></div>10+ requests</div>
    <div class="legend-note">Each corridor is a real driving route between neighbourhoods. Recent rides glow brightest. Half-life: 21 days.</div>
  </div>
</div>

<div class="footer-tag">Kyra · internal · snapshot Nov 2026</div>

<script>
const DATA = __DATA__;

document.getElementById('stat-rides').textContent = DATA.total_mapped.toLocaleString();
document.getElementById('stat-corridors').textContent = DATA.unique_corridors.toLocaleString();
document.getElementById('stat-top-count').textContent = (DATA.top_recency[0] ? DATA.top_recency[0].count : '—');
document.getElementById('stat-window').textContent = DATA.span_days;

const map = L.map('map', {
  center: [12.9716, 77.5946],
  zoom: 11, zoomControl: true, worldCopyJump: false, renderer: L.canvas(),
  maxBounds: [[12.55, 77.2], [13.35, 78.0]], maxBoundsViscosity: 0.8,
  minZoom: 11, maxZoom: 15,
});
L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Base/MapServer/tile/{z}/{y}/{x}', {
  attribution: 'Esri · OpenStreetMap · Routes © OSRM', maxZoom: 16,
}).addTo(map);
setTimeout(() => map.invalidateSize(), 50);

const placed = [];
DATA.localities
  .filter(l => !l.name.startsWith('PIN '))
  .map(l => ({...l, total: l.pickups + l.dropoffs}))
  .sort((a,b) => b.total - a.total)
  .forEach(l => {
    const dupe = placed.find(p => Math.abs(p.lat - l.lat) < 0.011 && Math.abs(p.lon - l.lon) < 0.011);
    if (dupe) return;
    placed.push(l);
    if (placed.length > 24) return;
    L.marker([l.lat, l.lon], {
      icon: L.divIcon({
        className: 'loc-label',
        html: `<span data-weight="${l.total}">${l.name}</span>`,
        iconSize: [1, 1], iconAnchor: [0, 0],
      }),
      interactive: false, keyboard: false,
    }).addTo(map);
  });

function updateLabels() {
  const z = map.getZoom();
  document.querySelectorAll('.loc-label span').forEach(el => {
    const w = parseInt(el.getAttribute('data-weight')) || 1;
    const base = z <= 11 ? 9 : z === 12 ? 11 : z === 13 ? 13 : 15;
    const bump = Math.min(Math.sqrt(w) * 0.35, 3);
    el.style.fontSize = (base + bump) + 'px';
    el.style.opacity = (z < 12 && w < 10) ? 0 : 1;
  });
}
map.on('zoomend', updateLabels);
setTimeout(updateLabels, 100);

map.fitBounds([[12.84, 77.47], [13.12, 77.78]]);

const corridorLayer = L.layerGroup().addTo(map);
let pickupMarkers = null, dropMarkers = null;

function colorFor(c) {
  if (c.c >= 10) return '#ffcc33';
  if (c.c >= 5) return '#ff8833';
  if (c.c >= 2) return '#ff4d7a';
  return '#ff3860';
}
function weightFor(c) {
  if (c.c >= 10) return 6;
  if (c.c >= 5) return 4.2;
  if (c.c >= 2) return 2.5;
  return 1.3;
}
function opacityFor(c) {
  const base = c.c >= 10 ? 0.95 : c.c >= 5 ? 0.75 : c.c >= 2 ? 0.5 : 0.25;
  if (c.r > 0) return Math.min(1, base + 0.15);
  return base;
}
function fmtAgo(iso) {
  if (!iso) return '—';
  const then = new Date(iso);
  const diffDays = Math.round((new Date(DATA.now) - then) / 86400000);
  if (diffDays <= 0) return 'today';
  if (diffDays === 1) return '1 d ago';
  if (diffDays < 30) return diffDays + ' d ago';
  const m = Math.floor(diffDays / 30);
  return m + ' mo ago';
}

function drawCorridors() {
  corridorLayer.clearLayers();
  const sorted = [...DATA.corridors].sort((a, b) => a.c - b.c);
  sorted.forEach(c => {
    const latlngs = c.g.map(p => [p[1], p[0]]);
    const poly = L.polyline(latlngs, {
      color: colorFor(c), weight: weightFor(c), opacity: opacityFor(c),
      smoothFactor: 1.2, lineCap: 'round', lineJoin: 'round',
    });
    if (c.c >= 3) {
      poly.bindPopup(`
        <div class="popup-head">${c.f} → ${c.t}</div>
        <div class="popup-stat"><b>${c.c}</b> requests total · <b>${c.r}</b> in last 30 d</div>
        <div class="popup-stat">${c.d} km · ${c.m} min route</div>
      `);
    }
    corridorLayer.addLayer(poly);
  });
}

function makeLocalityMarkers(mode) {
  const markers = [];
  DATA.localities.forEach(l => {
    const val = mode === 'pickups' ? l.pickups : l.dropoffs;
    if (val === 0) return;
    const r = Math.min(4 + Math.sqrt(val) * 2.3, 32);
    const alpha = Math.min(0.25 + val / 60, 0.85);
    const marker = L.circleMarker([l.lat, l.lon], {
      radius: r, color: '#ffcc33',
      fillColor: mode === 'pickups' ? '#ffcc33' : '#ff4d7a',
      fillOpacity: alpha, weight: 1.4, opacity: 0.9,
    });
    marker.bindPopup(`
      <div class="popup-head">${l.name}</div>
      <div class="popup-stat"><b>${val}</b> ${mode === 'pickups' ? 'pickups' : 'drop-offs'}</div>
      <div class="popup-stat"><b>${mode === 'pickups' ? l.pickups_recent : l.dropoffs_recent}</b> in last 30 d</div>
    `);
    markers.push(marker);
  });
  return L.layerGroup(markers);
}

function setView(view) {
  corridorLayer.remove();
  if (pickupMarkers) map.removeLayer(pickupMarkers);
  if (dropMarkers) map.removeLayer(dropMarkers);
  if (view === 'corridors') corridorLayer.addTo(map);
  else if (view === 'pickups') {
    if (!pickupMarkers) pickupMarkers = makeLocalityMarkers('pickups');
    pickupMarkers.addTo(map);
  } else if (view === 'dropoffs') {
    if (!dropMarkers) dropMarkers = makeLocalityMarkers('dropoffs');
    dropMarkers.addTo(map);
  }
}

document.querySelectorAll('.toggle-btn').forEach(btn => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('.toggle-btn').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    setView(btn.dataset.view);
  });
});

function renderList(mode) {
  const list = mode === 'recency' ? DATA.top_recency : mode === 'volume' ? DATA.top_volume : DATA.top_last30;
  const ul = document.getElementById('top-list');
  ul.innerHTML = '';
  if (!list.length) {
    ul.innerHTML = '<li style="color: var(--muted); font-size: 11px;">No data in this window.</li>';
    return;
  }
  list.forEach((c, i) => {
    const li = document.createElement('li');
    li.innerHTML = `
      <div><span class="rank">${i + 1}</span><span class="route">${c.f}<span class="arrow">→</span>${c.t}</span></div>
      <div class="meta">
        <span class="count-pill">${c.count ?? c.c} reqs</span>
        <span class="recent-pill">${c.recent ?? c.r ?? 0} in 30 d</span>
        <span class="ago">last ${fmtAgo(c.last)}</span>
      </div>
    `;
    li.addEventListener('click', () => {
      const corr = DATA.corridors.find(x => x.f === c.f && x.t === c.t);
      if (corr) {
        const bounds = L.latLngBounds(corr.g.map(p => [p[1], p[0]]));
        map.fitBounds(bounds, { padding: [100, 100], maxZoom: 14 });
      }
    });
    ul.appendChild(li);
  });
}

document.querySelectorAll('.collapse-btn').forEach(btn => {
  btn.addEventListener('click', (e) => {
    e.stopPropagation();
    const target = document.getElementById(btn.dataset.target);
    if (target) target.classList.toggle('collapsed');
  });
});
if (window.matchMedia('(max-width: 760px)').matches) {
  ['masthead', 'panel', 'legend'].forEach(id => {
    const el = document.getElementById(id);
    if (el) el.classList.add('collapsed');
  });
}

document.querySelectorAll('.sort-tab').forEach(t => {
  t.addEventListener('click', () => {
    document.querySelectorAll('.sort-tab').forEach(x => x.classList.remove('active'));
    t.classList.add('active');
    renderList(t.dataset.sort);
  });
});

drawCorridors();
renderList('recency');
</script>
</body>
</html>
'''

if __name__ == '__main__':
    main()
