#!/usr/bin/env python3
"""
SIA Parser v4 — Format XML natif SIA (Ase/Abd corrigé)
Usage:
    python3 sia_parser_v4.py --input AIXM4.5_all_FR_OM_2026-06-11.xml
Sortie:
    airspaces_sudouest_drones.geojson
"""

import json, math, re, sys, os, argparse
from lxml import etree
from collections import defaultdict

BBOX = dict(lon_min=-2.5, lat_min=42.0, lon_max=3.5, lat_max=46.5)
DRONE_MAX_FT = 400

ZONE_TYPES = {
    'P':    {'label':'Zone Interdite',    'color':'#CC0000','opacity':0.65},
    'R':    {'label':'Zone Réglementée', 'color':'#FF5500','opacity':0.55},
    'D':    {'label':'Zone Dangereuse',  'color':'#FF9900','opacity':0.48},
    'CTR':  {'label':'CTR',              'color':'#1a6bff','opacity':0.40},
    'TMA':  {'label':'TMA',              'color':'#0090bb','opacity':0.28},
    'SIV':  {'label':'SIV',              'color':'#00aa66','opacity':0.22},
    'RTBA': {'label':'RTBA',             'color':'#8800cc','opacity':0.50},
    'ATZ':  {'label':'ATZ',              'color':'#3a6090','opacity':0.38},
    'RMZ':  {'label':'RMZ',              'color':'#44aadd','opacity':0.35},
    'TMZ':  {'label':'TMZ',              'color':'#33cc66','opacity':0.30},
    'ZSM':  {'label':'Zone Sensible',    'color':'#ff3399','opacity':0.40},
    'CTA':  {'label':'CTA',              'color':'#0066aa','opacity':0.22},
}

# Types SIA → type normalisé
TYPE_MAP = {
    'P':'P','R':'R','D':'D','CTR':'CTR','TMA':'TMA','CTA':'CTA',
    'ATZ':'ATZ','SIV':'SIV','RMZ':'RMZ','TMZ':'TMZ','RTBA':'RTBA','ZSM':'ZSM',
}

def t(el, tag):
    """Texte d'un sous-élément."""
    f = el.find(tag)
    return f.text.strip() if f is not None and f.text else None

def parse_geo(val):
    """'DDMMSS.ssN' ou 'DDDMMSS.ssE' → degrés décimaux."""
    val = val.strip()
    hemi = val[-1]
    digits = val[:-1]
    if hemi in ('N','S'):
        d,m,s = int(digits[:2]), int(digits[2:4]), float(digits[4:])
    else:
        d,m,s = int(digits[:3]), int(digits[3:5]), float(digits[5:])
    dd = d + m/60.0 + s/3600.0
    return -dd if hemi in ('S','W') else dd

def parse_alt(val_str, uom):
    try: val = float(val_str)
    except: return 0.0
    uom = (uom or '').upper()
    if uom == 'FL': return val * 100.0
    if uom == 'M':  return val * 3.28084
    return val  # FT par défaut

def make_circle(lat_c, lon_c, r_nm, n=48):
    pts = []
    for i in range(n+1):
        a = math.radians(i*360.0/n)
        lat = lat_c + (r_nm/60.0)*math.cos(a)
        lon = lon_c + (r_nm/60.0)/math.cos(math.radians(lat_c))*math.sin(a)
        pts.append([round(lon,5), round(lat,5)])
    return pts

def in_bbox(coords):
    if not coords: return False
    lons = [c[0] for c in coords]
    lats = [c[1] for c in coords]
    return (max(lons)>=BBOX['lon_min'] and min(lons)<=BBOX['lon_max'] and
            max(lats)>=BBOX['lat_min'] and min(lats)<=BBOX['lat_max'])

def parse_sia_xml(path):
    print(f"[→] Parsing {path} ...")
    tree = etree.parse(path)
    root = tree.getroot()

    # ── 1. Lire tous les Ase ──────────────────────────────────────
    ase_dict = {}  # codeId → props

    for ase in root.findall('.//Ase'):
        # codeId est dans AseUid
        uid = ase.find('.//AseUid')
        if uid is None: continue
        code_id   = t(uid, 'codeId') or ''
        code_type = t(uid, 'codeType') or ''

        local_type = t(ase, 'txtLocalType') or ''
        name       = t(ase, 'txtName') or code_id

        # Normaliser le type
        atype = TYPE_MAP.get(code_type.upper())
        if not atype:
            atype = TYPE_MAP.get(local_type.upper())
        if not atype:
            continue

        # Altitudes
        val_u = t(ase, 'valDistVerUpper')
        uom_u = t(ase, 'uomDistVerUpper')
        val_l = t(ase, 'valDistVerLower')
        uom_l = t(ase, 'uomDistVerLower')

        upper_ft = parse_alt(val_u, uom_u)
        lower_ft = parse_alt(val_l, uom_l)

        if lower_ft > DRONE_MAX_FT:
            continue

        ase_dict[code_id] = {
            'id': code_id, 'name': name, 'type': atype,
            'lower_ft': lower_ft, 'upper_ft': upper_ft,
            'lower_str': f"{val_l or 'SFC'} {uom_l or ''}".strip(),
            'upper_str': f"{val_u or '?'} {uom_u or ''}".strip(),
        }

    print(f"[i] {len(ase_dict)} Ase pertinents (plancher ≤ {DRONE_MAX_FT} ft)")

    # ── 2. Lire toutes les Abd et regrouper les points ────────────
    # Chaque Abd a UNE AseUid + UN ou PLUSIEURS Avx
    # Plusieurs Abd peuvent partager le même codeId → former le polygone
    geo_dict = defaultdict(list)  # codeId → [points ordonnés]

    for abd in root.findall('.//Abd'):
        # Trouver le codeId via AbdUid/AseUid
        ase_uid = abd.find('.//AseUid')
        if ase_uid is None: continue
        code_id = t(ase_uid, 'codeId')
        if not code_id or code_id not in ase_dict: continue

        # Lire tous les Avx de cet Abd
        for avx in abd.findall('.//Avx'):
            avx_type = t(avx, 'codeType') or 'GRC'
            lat_el   = avx.find('geoLat')
            lon_el   = avx.find('geoLong')

            if lat_el is not None and lon_el is not None and lat_el.text and lon_el.text:
                try:
                    lat = parse_geo(lat_el.text)
                    lon = parse_geo(lon_el.text)
                    geo_dict[code_id].append([round(lon,5), round(lat,5)])
                except Exception as e:
                    pass

            # Arc de cercle
            if avx_type in ('ABE','ABN','CWA','CCA'):
                c_lat_el = avx.find('geoLatArc')
                c_lon_el = avx.find('geoLongArc')
                r_el     = avx.find('valRadiusArc')
                if c_lat_el is not None and c_lon_el is not None and r_el is not None:
                    try:
                        c_lat = parse_geo(c_lat_el.text)
                        c_lon = parse_geo(c_lon_el.text)
                        r_nm  = float(r_el.text)
                        arc_pts = make_circle(c_lat, c_lon, r_nm, n=32)
                        geo_dict[code_id].extend(arc_pts[::4])
                    except:
                        pass

    print(f"[i] Géométries : {len(geo_dict)} espaces avec points")

    # ── 3. Assembler les features GeoJSON ─────────────────────────
    features = []
    stats = defaultdict(int)
    no_geo = 0

    for code_id, ase in ase_dict.items():
        coords = geo_dict.get(code_id, [])

        if len(coords) < 3:
            no_geo += 1
            continue

        if coords[0] != coords[-1]:
            coords.append(coords[0])

        if not in_bbox(coords):
            continue

        atype  = ase['type']
        style  = ZONE_TYPES.get(atype, {'color':'#888','opacity':0.3})
        lo_m   = round(ase['lower_ft']*0.3048, 1)
        up_m   = round(min(ase['upper_ft'], DRONE_MAX_FT)*0.3048, 1)

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
                'height_m':   max(up_m-lo_m, 5),
                'color':      style['color'],
                'opacity':    style['opacity'],
            }
        })
        stats[atype] += 1

    if no_geo:
        print(f"[i] {no_geo} espaces sans géométrie suffisante (ignorés)")

    return features, stats

def export_geojson(features, output):
    from datetime import datetime
    gj = {
        'type': 'FeatureCollection',
        'metadata': {
            'source': 'SIA DGAC — XML natif AIRAC 06/26',
            'generated': datetime.utcnow().isoformat()+'Z',
            'drone_max_ft': DRONE_MAX_FT,
            'bbox': BBOX,
            'count': len(features),
            'airac': '06/26',
        },
        'features': features
    }
    with open(output, 'w', encoding='utf-8') as f:
        json.dump(gj, f, ensure_ascii=False, separators=(',',':'))
    kb = os.path.getsize(output)//1024
    print(f"[✓] {output} → {len(features)} zones ({kb} Ko)")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--input',  '-i', required=True)
    ap.add_argument('--output', '-o', default='airspaces_sudouest_drones.geojson')
    args = ap.parse_args()

    if not os.path.exists(args.input):
        print(f"[!] Fichier introuvable : {args.input}")
        sys.exit(1)

    print("="*60)
    print("  SIA Parser v4 — Format XML natif SIA")
    print(f"  Zone : Sud-Ouest France | Limite : {DRONE_MAX_FT} ft / 120 m")
    print("="*60)

    features, stats = parse_sia_xml(args.input)
    export_geojson(features, args.output)

    print()
    print("[✓] Zones par type :")
    for tp, n in sorted(stats.items()):
        label = ZONE_TYPES.get(tp, {}).get('label', tp)
        print(f"    {tp:6s} — {label:20s} : {n}")

if __name__ == '__main__':
    main()
