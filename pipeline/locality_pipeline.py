#!/usr/bin/env python3
"""Fast locality-level pipeline: extract neighborhoods, geocode each, route between pairs."""
import json, re, time, os
from datetime import datetime
from collections import defaultdict
from urllib.parse import quote
from urllib.request import Request, urlopen

SCRATCH = os.path.dirname(os.path.abspath(__file__))
BOOKINGS = os.path.join(SCRATCH, 'bookings.json')
OUT_LOCS = os.path.join(SCRATCH, 'localities.json')
OUT_ROUTES = os.path.join(SCRATCH, 'locality_routes.json')
PROGRESS = os.path.join(SCRATCH, 'progress.txt')

UA = 'KyraDemandCorridorsMap/1.0 (contact via admin)'

LOCALITIES = [
    'MG Road', 'Brigade Road', 'UB City', 'Cubbon Park', 'Vidhana Soudha', 'Shivaji Nagar',
    'Fraser Town', 'Richmond Town', 'Shanti Nagar', 'Shanthi Nagar', 'Langford Town',
    'Lavelle Road', 'Infantry Road', 'Commercial Street', 'Church Street',
    'Majestic', 'Gandhi Nagar', 'Chickpet', 'Cottonpete', 'Balepete',
    'KR Market', 'K.R. Market', 'City Market', 'Sampangi Rama Nagar',
    'Jayanagar 9th Block', 'Jayanagar', 'J. P. Nagar', 'J.P. Nagar', 'JP Nagar', 'Banashankari 3rd Stage', 'Banashankari 2nd Stage', 'Banashankari 1st Stage', 'Banashankari',
    'Basavanagudi', 'Basavangudi', 'Padmanabhanagar', 'Kumaraswamy Layout', 'Kumara Swamy Layout',
    'Kathreguppe', 'Girinagar', 'Hanumanthanagar',
    'BTM 2nd Stage', 'BTM 1st Stage', 'BTM Layout', 'BTM',
    'Bommanahalli', 'Hongasandra', 'Begur', 'Hulimavu', 'Arekere', 'Gottigere',
    'Bannerghatta Road', 'Bannerghatta', 'Kanakapura Road', 'Kanakapura',
    'Jigani', 'Anjanapura', 'Hulimavu',
    'HSR Layout', 'HSR', 'Sector 2 HSR', 'Sector 7 HSR',
    'Koramangala 1st Block', 'Koramangala 4th Block', 'Koramangala 5th Block', 'Koramangala 6th Block', 'Koramangala 8th Block', 'Koramangala',
    'Ejipura', 'Sarjapur Road', 'Sarjapur', 'Bellandur', 'Haralur', 'Kodathi', 'Kasavanahalli',
    'Agara', 'Iblur', 'Panathur',
    'Indiranagar', 'Domlur', 'CV Raman Nagar', 'C.V. Raman Nagar', 'Halasuru', 'Ulsoor',
    'Murugeshpalya', 'Byappanahalli', 'Benniganahalli', 'Tin Factory',
    'Marathahalli', 'Brookefield', 'Kundalahalli', 'Doddanekkundi', 'Mahadevapura', 'Hoodi', 'Kadugodi',
    'Whitefield', 'ITPL', 'Varthur', 'Gunjur', 'Immadihalli',
    'KR Puram', 'K. R. Puram', 'Ramamurthy Nagar', 'Horamavu', 'Kasturi Nagar', 'Kalyan Nagar',
    'Hennur', 'HBR Layout', 'Banaswadi', 'Kammanahalli', 'Nagawara', 'Nagavara',
    'Thanisandra', 'Thanisandra Main Road', 'K Narayanapura', 'Kothanur', 'RK Hegde Nagar',
    'Manyata Tech Park', 'Manayata Tech Park',
    'RT Nagar', 'R.T. Nagar', 'Sanjaynagar', 'Sanjay Nagar', 'Sahakarnagar', 'Sahakar Nagar',
    'Hebbal', 'Yelahanka', 'Yelahanka New Town', 'Jakkur', 'Vidyaranyapura', 'Kodigehalli',
    'Mathikere', 'MS Ramaiah', 'M.S. Ramaiah', 'Gokula',
    'Malleshwaram', 'Malleswaram', 'Rajajinagar', 'Rajaji Nagar', 'Mahalakshmi Layout', 'Peenya',
    'Vijayanagar', 'Chord Road', 'Basaveshwar Nagar', 'Basaveshwara Nagar', 'Nagarbhavi', 'Nayandahalli',
    'Mysore Road', 'Mysore Rd', 'Kengeri',
    'Jnanabharathi', 'Rajarajeshwari Nagar', 'RR Nagar',
    'Electronic City', 'Bommasandra', 'Konanakunte', 'Chikkabanavara', 'Hosakerehalli',
    'Devanahalli', 'KIA', 'Bangalore Airport',
    'Seshadripuram', 'Vasanth Nagar', 'Palace Road', 'High Grounds', 'Benson Town',
    # Added based on fallthrough analysis
    'Dooravani Nagar', 'Ashok Nagar', 'S.G. Palya', 'SG Palya', 'Subramanyapura', 'Armane Nagar',
    'Yellappa Chetty Layout', 'Adugodi', 'Rustam Bagh Layout', 'Lingarajapuram', 'Cox Town',
    'Bendre Nagar', 'Kodihalli', 'Kaggadasapura', 'KPC Layout', 'Maruthi Sevanagar',
    'Nehru Nagar', 'Bilekahalli', 'Krishnarajapuram', 'Shankarapura', 'Narayanapura',
    'Mangammanapalya', 'Akshayanagar', 'Hegganahalli', 'Annapurneshwari Nagar',
    'T. Dasarahalli', 'Dasarahalli', 'Medahalli', 'Battarahalli', 'Panduranga Nagar',
    'Virupakshapura', 'Ramesh Nagar', 'Vimanapura', 'Nayanda Halli', 'Guddadahalli',
    'SMV Layout', 'Sudhama Nagar', 'Jagajeevanram Nagar', 'Kadugondanahalli',
    'Sampigehalli', 'Kempegowda Nagar', 'Mahalakshmipuram', 'Devara Jeevanahalli',
    'Chamrajpet', 'Kamakshipalya', 'Binnipete', 'Jalahalli', 'Yeshwanthpura',
    'Vivek Nagar', 'Austin Town', 'Byatarayanapura', 'Jeevan Bima Nagar',
    'Vibhutipura', 'Sadduguntepalya', 'Sivanchetti Gardens', 'Shanthala Nagar',
    'Bhavani Nagar', 'Chikku Lakshmaiah Layout', 'Vinobha Nagar', 'Kalena Agrahara',
    'Gottigere', 'Yelachenahalli', 'Nyanapanahalli', 'Hosakerehalli', 'Konanakunte Cross',
    'Mallathahalli', 'Herohalli', 'Nagarabhavi', 'Chikkalasandra', 'Thalaghattapura',
    'Haralur Road', 'Bommanahalli', 'Chandra Layout', 'ISRO Layout', 'Agara Village',
    'Chikkallasandra', 'Raghuvanahalli', 'Hulimangala', 'Doddathoguru', 'Chamarajpet',
    'Kithaganur', 'Kadugodi Extension', 'Battarahalli Extension', 'Vignan Nagar',
    'Byatarayanapura CMC', 'Ganganagar', 'J.C. Nagar', 'JC Nagar', 'Kacharakanahalli',
    'Chikkabettahalli', 'Kurubarahalli', 'Vasanthpura', 'Kodigehalli Main Rd',
    'Puttenahalli', 'Deepanjali Nagar', 'Nagasandra', 'Dasarahalli (T)',
]

def extract_locality(addr):
    if not addr: return None
    for loc in LOCALITIES:
        if re.search(r'\b' + re.escape(loc) + r'\b', addr, re.IGNORECASE):
            return normalize(loc)
    pin = re.search(r'\b56\d{4}\b', addr)
    if pin:
        return f'PIN {pin.group(0)}'
    return None

def normalize(loc):
    t = loc.strip()
    t = re.sub(r'\s+', ' ', t)
    t = t.replace('J. P. Nagar', 'JP Nagar').replace('J.P. Nagar', 'JP Nagar')
    t = t.replace('K. R. Puram', 'KR Puram').replace('K.R. Puram', 'KR Puram')
    t = t.replace('C.V. Raman Nagar', 'CV Raman Nagar')
    t = t.replace('R.T. Nagar', 'RT Nagar').replace('Sanjay Nagar','Sanjaynagar').replace('Sahakar Nagar','Sahakarnagar')
    t = t.replace('Malleswaram', 'Malleshwaram')
    t = t.replace('Basaveshwara Nagar', 'Basaveshwar Nagar')
    t = t.replace('M.S. Ramaiah', 'MS Ramaiah')
    t = t.replace('K.R. Market', 'KR Market').replace('City Market','KR Market')
    t = t.replace('Basavangudi','Basavanagudi')
    t = t.replace('Kumara Swamy Layout','Kumaraswamy Layout')
    t = t.replace('Rajaji Nagar','Rajajinagar')
    t = t.replace('RR Nagar','Rajarajeshwari Nagar')
    t = t.replace('Nagavara','Nagawara').replace('Manayata Tech Park','Manyata Tech Park')
    t = re.sub(r'\bHSR\b(?! Layout)', 'HSR Layout', t)
    t = re.sub(r'\bBTM\b(?! \d.. Stage| Layout)', 'BTM Layout', t)
    t = re.sub(r'^Koramangala.*$', 'Koramangala', t) if t.startswith('Koramangala') else t
    t = re.sub(r'^Jayanagar.*$', 'Jayanagar', t) if t.startswith('Jayanagar') else t
    t = re.sub(r'^Banashankari.*$', 'Banashankari', t) if t.startswith('Banashankari') else t
    return t

def nominatim(q):
    url = f'https://nominatim.openstreetmap.org/search?q={quote(q)}&format=json&limit=1&countrycodes=in&viewbox=77.3,12.75,77.85,13.20&bounded=1'
    req = Request(url, headers={'User-Agent': UA, 'Accept': 'application/json'})
    try:
        with urlopen(req, timeout=15) as r:
            data = json.loads(r.read().decode('utf-8'))
            if data:
                return float(data[0]['lat']), float(data[0]['lon'])
    except Exception:
        return None

def osrm_route(lat1, lon1, lat2, lon2):
    url = f'https://router.project-osrm.org/route/v1/driving/{lon1},{lat1};{lon2},{lat2}?overview=full&geometries=geojson'
    req = Request(url, headers={'User-Agent': UA, 'Accept': 'application/json'})
    try:
        with urlopen(req, timeout=20) as r:
            data = json.loads(r.read().decode('utf-8'))
            if data.get('code') == 'Ok' and data.get('routes'):
                return {
                    'geom': data['routes'][0]['geometry']['coordinates'],
                    'distance_m': data['routes'][0]['distance'],
                    'duration_s': data['routes'][0]['duration'],
                }
    except Exception:
        return None

def log(m):
    t = time.strftime('%H:%M:%S')
    line = f'[{t}] {m}'
    print(line, flush=True)
    with open(PROGRESS, 'a') as f: f.write(line + '\n')

def parse_time(s):
    try:
        return datetime.strptime(s, '%d %b %Y, %I:%M %p')
    except Exception:
        try:
            return datetime.strptime(s.replace('Sept', 'Sep'), '%d %b %Y, %I:%M %p')
        except Exception:
            return None

def main():
    rides = json.load(open(BOOKINGS))
    log(f'Loaded {len(rides)} rides')

    out = []
    unlocatable_from = 0
    unlocatable_to = 0
    for r in rides:
        f_loc = extract_locality(r.get('from', ''))
        t_loc = extract_locality(r.get('to', ''))
        if not f_loc: unlocatable_from += 1
        if not t_loc: unlocatable_to += 1
        when = parse_time(r.get('time', ''))
        out.append({
            'from_loc': f_loc, 'to_loc': t_loc,
            'from_raw': r.get('from',''), 'to_raw': r.get('to',''),
            'rider': r.get('rider',''), 'status': r.get('status',''),
            'fare': r.get('fare',''), 'time': r.get('time',''),
            'when': when.isoformat() if when else None,
        })

    found = sum(1 for r in out if r['from_loc'] and r['to_loc'])
    log(f'Both ends resolved: {found}/{len(out)}; missing from={unlocatable_from} to={unlocatable_to}')

    uniq = set()
    for r in out:
        if r['from_loc']: uniq.add(r['from_loc'])
        if r['to_loc']: uniq.add(r['to_loc'])
    uniq = sorted(uniq)
    log(f'Unique localities: {len(uniq)}')

    loc_coords = {}
    if os.path.exists(OUT_LOCS):
        loc_coords = json.load(open(OUT_LOCS))
        log(f'Resuming geocode: {len(loc_coords)} cached')

    for i, loc in enumerate(uniq):
        if loc in loc_coords: continue
        q = loc if loc.startswith('PIN') else f'{loc}, Bengaluru, Karnataka, India'
        q = q.replace('PIN ', '')
        res = nominatim(q)
        loc_coords[loc] = {'lat': res[0], 'lon': res[1]} if res else None
        if (i+1) % 20 == 0:
            with open(OUT_LOCS, 'w') as f: json.dump(loc_coords, f)
            log(f'Geocoded {i+1}/{len(uniq)}')
        time.sleep(1.05)

    with open(OUT_LOCS, 'w') as f: json.dump(loc_coords, f)
    hits = sum(1 for v in loc_coords.values() if v)
    log(f'Geocoded {hits}/{len(loc_coords)} localities')

    pair_rides = defaultdict(list)
    for r in out:
        if not r['from_loc'] or not r['to_loc']: continue
        if r['from_loc'] == r['to_loc']: continue
        g1 = loc_coords.get(r['from_loc']); g2 = loc_coords.get(r['to_loc'])
        if not g1 or not g2: continue
        pair_rides[(r['from_loc'], r['to_loc'])].append(r)
    log(f'Routable OD pairs: {len(pair_rides)}')

    routes = {}
    if os.path.exists(OUT_ROUTES):
        routes = json.load(open(OUT_ROUTES))
        log(f'Resuming routes: {len(routes)} cached')

    pairs_sorted = sorted(pair_rides.items(), key=lambda x: -len(x[1]))
    for i, ((f,t), rs) in enumerate(pairs_sorted):
        key = f'{f}||{t}'
        if key in routes: continue
        g1 = loc_coords[f]; g2 = loc_coords[t]
        rt = osrm_route(g1['lat'], g1['lon'], g2['lat'], g2['lon'])
        routes[key] = rt
        if (i+1) % 25 == 0:
            with open(OUT_ROUTES, 'w') as f_: json.dump(routes, f_)
            log(f'Routed {i+1}/{len(pair_rides)}')
        time.sleep(1.05)

    with open(OUT_ROUTES, 'w') as f_: json.dump(routes, f_)
    log(f'Routes done: {sum(1 for v in routes.values() if v)}/{len(routes)}')

    with open(os.path.join(SCRATCH, 'rides_enriched.json'), 'w') as f_:
        json.dump(out, f_)
    log('DONE')

if __name__ == '__main__':
    main()
