#!/usr/bin/env python3
"""
SIA Parser v5 (corrigé) — Format XML natif SIA
- Correction parse_geo : gère DDMMSS.ssN ET DDMMSSN (sans décimales)
- Correction arcs CWA/CCA
- VOLTAC + PJE + PRN

Usage:
    python3 sia_parser_v5.py --input AIXM4.5_all_FR_OM_2026-06-11.xml
"""
import json, math, sys, os, argparse
from lxml import etree
from collections import defaultdict

BBOX = dict(lon_min=-2.5, lat_min=42.0, lon_max=3.5, lat_max=46.5)
DRONE_MAX_FT = 99999

ZONE_TYPES = {
    'P':     {'label':'Zone Interdite (P)',    'color':'#CC0000','opacity':0.65},
    'R':     {'label':'Zone Réglementée (R)', 'color':'#FF5500','opacity':0.55},
    'D':     {'label':'Zone Dangereuse (D)',  'color':'#FF9900','opacity':0.48},
    'CTR':   {'label':'CTR',                  'color':'#1a6bff','opacity':0.40},
    'TMA':   {'label':'TMA',                  'color':'#0090bb','opacity':0.28},
    'CTA':   {'label':'CTA',                  'color':'#0066aa','opacity':0.22},
    'SIV':   {'label':'SIV',                  'color':'#00aa66','opacity':0.22},
    'RTBA':  {'label':'RTBA',                 'color':'#8800cc','opacity':0.50},
    'ATZ':   {'label':'ATZ',                  'color':'#3a6090','opacity':0.38},
    'RMZ':   {'label':'RMZ',                  'color':'#44aadd','opacity':0.35},
    'TMZ':   {'label':'TMZ',                  'color':'#33cc66','opacity':0.30},
    'ZSM':   {'label':'Zone Sensible',        'color':'#ff3399','opacity':0.40},
    'VOLTAC':{'label':'VOLTAC',               'color':'#FF6600','opacity':0.45},
    'PJE':   {'label':'Zone Para (PJE)',      'color':'#cc6600','opacity':0.40},
    'TRA':   {'label':'Zone Transit (TRA)',   'color':'#884400','opacity':0.35},
    'PRN':   {'label':'Parc Naturel (PRN)',   'color':'#006633','opacity':0.30},
}

def normalize_type(code_type, local_type):
    ct = (code_type or '').strip().upper()
    lt = (local_type or '').strip().upper()
    direct = {'P','R','D','CTR','TMA','CTA','ATZ','RMZ','TMZ','TRA'}
    if ct in direct: return ct
    if ct == 'D-OTHER':
        return {'VOL':'VOLTAC','PJE':'PJE','PRN':'PRN','SUR':'R','TRVL':'R'}.get(lt)
    if ct == 'RAS':
        if lt == 'RMZ': return 'RMZ'
        if lt == 'FBZ': return 'CTR'
    return None

def parse_geo(val):
    """
    Parse SIA geo format — DEUX variantes :
      DDMMSS.ssN  → ex: 445832.00N, 0005251.00W
      DDMMSSN     → ex: 435010N, 0011806E  (sans décimales, sans point)
    """
    val = val.strip()
    hemi = val[-1]  # N/S/E/W
    digits = val[:-1]

    # Séparer la partie entière de la partie décimale
    if '.' in digits:
        int_part, dec_part = digits.split('.')
    else:
        int_part = digits
        dec_part = '00'

    if hemi in ('N', 'S'):
        # Latitude : DD MM SS
        if len(int_part) == 6:
            d, m, s = int(int_part[:2]), int(int_part[2:4]), float(int_part[4:6] + '.' + dec_part)
        elif len(int_part) == 5:
            d, m, s = int(int_part[:2]), int(int_part[2:4]), float(int_part[4:5] + '.' + dec_part)
        else:
            d, m, s = int(int_part[:2]), int(int_part[2:4]), 0.0
    else:
        # Longitude : DDD MM SS
        if len(int_part) == 7:
            d, m, s = int(int_part[:3]), int(int_part[3:5]), float(int_part[5:7] + '.' + dec_part)
        elif len(int_part) == 6:
            d, m, s = int(int_part[:3]), int(int_part[3:5]), float(int_part[5:6] + '.' + dec_part)
        else:
            d, m, s = int(int_part[:3]), int(int_part[3:5]), 0.0

    dd = d + m / 60.0 + s / 3600.0
    return -dd if hemi in ('S', 'W') else dd

def parse_alt(val_str, uom):
    try: val = float(val_str)
    except: return 0.0
    uom = (uom or '').upper()
    if uom == 'FL': return val * 100.0
    if uom == 'M':  return val * 3.28084
    return val

def bearing(c_lat, c_lon, p_lat, p_lon):
    """Bearing depuis le centre vers un point (degrés)"""
    dlat = math.radians(p_lat - c_lat)
    dlon = math.radians(p_lon - c_lon) * math.cos(math.radians(c_lat))
    return math.degrees(math.atan2(dlon, dlat)) % 360

def arc_points(c_lat, c_lon, r_nm, start_brg, end_brg, clockwise, n=24):
    """Interpoler un arc entre deux bearings depuis un centre.
    Prend toujours le chemin le plus court (< 180°) sauf si l'arc
    est vraiment long (zones militaires étendues).
    """
    pts = []
    r_deg_lat = r_nm / 60.0
    r_deg_lon = r_nm / 60.0 / math.cos(math.radians(c_lat))

    # Normaliser les bearings en [0, 360)
    start_brg = start_brg % 360
    end_brg   = end_brg   % 360

    if clockwise:
        # Arc horaire : de start vers end en allant dans le sens des aiguilles
        if end_brg < start_brg:
            sweep = end_brg + 360 - start_brg  # ex: start=350, end=10 → sweep=20°
        else:
            sweep = end_brg - start_brg          # ex: start=10, end=100 → sweep=90°
        # Si le sweep est > 350°, c'est probablement une erreur → prendre le complément
        if sweep > 350:
            sweep = 360 - sweep
            clockwise = False  # inverser le sens
    else:
        # Arc anti-horaire : de start vers end en sens inverse
        if start_brg < end_brg:
            sweep = start_brg + 360 - end_brg
        else:
            sweep = start_brg - end_brg
        if sweep > 350:
            sweep = 360 - sweep
            clockwise = True

    for i in range(n + 1):
        if clockwise:
            brg = math.radians((start_brg + sweep * i / n) % 360)
        else:
            brg = math.radians((start_brg - sweep * i / n) % 360)
        lat = c_lat + r_deg_lat * math.cos(brg)
        lon = c_lon + r_deg_lon * math.sin(brg)
        pts.append([round(lon, 5), round(lat, 5)])

    return pts

def in_bbox(coords):
    if not coords: return False
    lons = [c[0] for c in coords]
    lats = [c[1] for c in coords]
    return (max(lons) >= BBOX['lon_min'] and min(lons) <= BBOX['lon_max'] and
            max(lats) >= BBOX['lat_min'] and min(lats) <= BBOX['lat_max'])

def parse_sia_xml(path):
    print(f"[→] Parsing {path} ...")
    tree = etree.parse(path)
    root = tree.getroot()

    def tv(el, tag):
        f = el.find(tag)
        return f.text.strip() if f is not None and f.text else None

    # ── 1. Lire les Ase ──────────────────────────────────────────
    ase_dict = {}
    for ase in root.findall('.//Ase'):
        uid = ase.find('.//AseUid')
        if uid is None: continue
        code_id   = tv(uid, 'codeId') or ''
        code_type = tv(uid, 'codeType') or ''
        local_type= tv(ase, 'txtLocalType') or ''
        name      = tv(ase, 'txtName') or code_id

        atype = normalize_type(code_type, local_type)
        if not atype: continue

        val_u = tv(ase, 'valDistVerUpper')
        uom_u = tv(ase, 'uomDistVerUpper')
        val_l = tv(ase, 'valDistVerLower')
        uom_l = tv(ase, 'uomDistVerLower')

        upper_ft = parse_alt(val_u, uom_u)
        lower_ft = parse_alt(val_l, uom_l)
        if lower_ft > DRONE_MAX_FT: continue

        ase_dict[code_id] = {
            'id': code_id, 'name': name, 'type': atype,
            'lower_ft': lower_ft, 'upper_ft': upper_ft,
            'lower_str': f"{val_l or 'SFC'} {uom_l or ''}".strip(),
            'upper_str': f"{val_u or '?'} {uom_u or ''}".strip(),
        }

    print(f"[i] {len(ase_dict)} Ase pertinents")

    # ── 2. Lire les Abd avec arcs correctement interpolés ─────────
    geo_dict = defaultdict(list)
    arc_errors = 0

    for abd in root.findall('.//Abd'):
        ase_uid = abd.find('.//AseUid')
        if ase_uid is None: continue
        code_id = tv(ase_uid, 'codeId')
        if not code_id or code_id not in ase_dict: continue

        avxs = abd.findall('.//Avx')
        prev_lat = None
        prev_lon = None

        for avx in avxs:
            avx_type = tv(avx, 'codeType') or 'GRC'
            lat_el   = avx.find('geoLat')
            lon_el   = avx.find('geoLong')

            if lat_el is None or lon_el is None: continue

            try:
                end_lat = parse_geo(lat_el.text)
                end_lon = parse_geo(lon_el.text)
            except Exception as e:
                continue

            if avx_type in ('CWA', 'CCA'):
                # Arc de cercle
                c_lat_el = avx.find('geoLatArc')
                c_lon_el = avx.find('geoLongArc')
                r_el     = avx.find('valRadiusArc')
                uom_el   = avx.find('uomRadiusArc')

                if (c_lat_el is not None and c_lon_el is not None and
                    r_el is not None and prev_lat is not None):
                    try:
                        c_lat = parse_geo(c_lat_el.text)
                        c_lon = parse_geo(c_lon_el.text)
                        r_nm  = float(r_el.text)
                        uom   = (uom_el.text if uom_el is not None else 'NM').upper()
                        if uom == 'KM': r_nm /= 1.852
                        if uom == 'M':  r_nm /= 1852

                        start_brg = bearing(c_lat, c_lon, prev_lat, prev_lon)
                        end_brg   = bearing(c_lat, c_lon, end_lat, end_lon)
                        clockwise = (avx_type == 'CWA')

                        arc_pts = arc_points(c_lat, c_lon, r_nm, start_brg, end_brg, clockwise)
                        geo_dict[code_id].extend(arc_pts)
                    except Exception as e:
                        arc_errors += 1
                        geo_dict[code_id].append([round(end_lon, 5), round(end_lat, 5)])
                else:
                    geo_dict[code_id].append([round(end_lon, 5), round(end_lat, 5)])
            else:
                # GRC / RHL — ligne droite
                geo_dict[code_id].append([round(end_lon, 5), round(end_lat, 5)])

            prev_lat = end_lat
            prev_lon = end_lon

    print(f"[i] Géométries : {len(geo_dict)} espaces — {arc_errors} erreurs d'arc ignorées")

    # ── 3. Assembler GeoJSON ──────────────────────────────────────
    features = []
    stats    = defaultdict(int)
    skipped  = 0

    for code_id, ase in ase_dict.items():
        coords = geo_dict.get(code_id, [])
        if len(coords) < 3:
            skipped += 1
            continue
        if coords[0] != coords[-1]:
            coords.append(coords[0])
        if not in_bbox(coords):
            continue

        atype  = ase['type']
        style  = ZONE_TYPES.get(atype, {'color':'#888888','opacity':0.3})
        lo_m   = round(ase['lower_ft'] * 0.3048, 1)
        up_m   = round(min(ase['upper_ft'], DRONE_MAX_FT) * 0.3048, 1)

        features.append({
            'type': 'Feature',
            'geometry': {'type':'Polygon','coordinates':[coords]},
            'properties': {
                'id':         code_id,
                'name':       ase['name'],
                'type':       atype,
                'type_label': style['label'],
                'class':      '',
                'lower_ft':   ase['lower_ft'],
                'upper_ft':   ase['upper_ft'],
                'lower_str':  ase['lower_str'],
                'upper_str':  ase['upper_str'],
                'lower_m':    lo_m,
                'upper_m':    max(up_m, 5),
                'height_m':   max(up_m - lo_m, 5),
                'color':      style['color'],
                'opacity':    style['opacity'],
            }
        })
        stats[atype] += 1

    if skipped:
        print(f"[i] {skipped} espaces sans géométrie (ignorés)")

    return features, stats

def export_geojson(features, output):
    from datetime import datetime
    gj = {
        'type': 'FeatureCollection',
        'metadata': {
            'source':       'SIA DGAC — XML natif AIRAC 06/26',
            'generated':    datetime.utcnow().isoformat()+'Z',
            'drone_max_ft': DRONE_MAX_FT,
            'bbox':         BBOX,
            'count':        len(features),
            'airac':        '06/26',
        },
        'features': features
    }
    with open(output, 'w', encoding='utf-8') as f:
        json.dump(gj, f, ensure_ascii=False, separators=(',',':'))
    kb = os.path.getsize(output) // 1024
    print(f"[✓] {output} → {len(features)} zones ({kb} Ko)")

def main():
    ap = argparse.ArgumentParser(description='SIA XML → GeoJSON drones Sud-Ouest')
    ap.add_argument('--input',  '-i', required=True)
    ap.add_argument('--output', '-o', default='airspaces_sudouest_drones.geojson')
    args = ap.parse_args()

    if not os.path.exists(args.input):
        print(f"[!] Fichier introuvable : {args.input}")
        sys.exit(1)

    print("="*60)
    print("  SIA Parser v5 (corrigé) — Format XML natif SIA")
    print(f"  Zone : Sud-Ouest France | Limite : {DRONE_MAX_FT} ft / FL115")
    print("="*60)

    features, stats = parse_sia_xml(args.input)
    export_geojson(features, args.output)

    print(f"\n[✓] {sum(stats.values())} zones — détail :")
    for tp, n in sorted(stats.items()):
        label = ZONE_TYPES.get(tp, {}).get('label', tp)
        print(f"    {tp:8s} — {label:25s} : {n}")

if __name__ == '__main__':
    main()
