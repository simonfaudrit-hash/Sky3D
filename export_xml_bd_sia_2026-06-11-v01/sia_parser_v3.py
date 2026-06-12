#!/usr/bin/env python3
"""
SIA Parser v3 — Format XML natif SIA (Ase/Abd)
================================================
Compatible avec AIXM4.5_all_FR_OM_YYYY-MM-DD.xml

Usage:
    python3 sia_parser_v3.py --input AIXM4.5_all_FR_OM_2026-06-11.xml

Sortie:
    airspaces_sudouest_drones.geojson
"""

import json, math, re, sys, os, argparse
from lxml import etree
from collections import defaultdict

# ── Config ────────────────────────────────────────────────────────
BBOX = dict(lon_min=-2.5, lat_min=42.0, lon_max=3.5, lat_max=46.5)
DRONE_MAX_FT = 400  # 120 m

ZONE_TYPES = {
    'P':    {'label': 'Zone Interdite',    'color': '#CC0000', 'opacity': 0.65},
    'R':    {'label': 'Zone Réglementée', 'color': '#FF5500', 'opacity': 0.55},
    'D':    {'label': 'Zone Dangereuse',  'color': '#FF9900', 'opacity': 0.48},
    'CTR':  {'label': 'CTR',              'color': '#1a6bff', 'opacity': 0.40},
    'TMA':  {'label': 'TMA',              'color': '#0090bb', 'opacity': 0.28},
    'SIV':  {'label': 'SIV',              'color': '#00aa66', 'opacity': 0.22},
    'RTBA': {'label': 'RTBA',             'color': '#8800cc', 'opacity': 0.50},
    'ATZ':  {'label': 'ATZ',              'color': '#3a6090', 'opacity': 0.38},
    'RMZ':  {'label': 'RMZ',             'color': '#44aadd', 'opacity': 0.35},
    'TMZ':  {'label': 'TMZ',             'color': '#33cc66', 'opacity': 0.30},
    'ZSM':  {'label': 'Zone Sensible',   'color': '#ff3399', 'opacity': 0.40},
    'CTA':  {'label': 'CTA',             'color': '#0066aa', 'opacity': 0.22},
}

# Correspondance codeType SIA → type normalisé
TYPE_MAP = {
    'P': 'P', 'R': 'R', 'D': 'D',
    'CTR': 'CTR', 'TMA': 'TMA', 'CTA': 'CTA',
    'ATZ': 'ATZ', 'SIV': 'SIV', 'RMZ': 'RMZ', 'TMZ': 'TMZ',
    'RTBA': 'RTBA', 'ZSM': 'ZSM',
}

# ── Parse coordonnée SIA : "DDMMSS.ssN" → degrés décimaux ─────────
def parse_geo(val):
    """
    Parse le format SIA : '470440.00N', '0020137.00E', '0032624.00W'
    Longitude : 3 chiffres pour degrés (DDDMMSS.ss)
    Latitude  : 2 chiffres pour degrés (DDMMSS.ss)
    """
    val = val.strip()
    hemi = val[-1]
    digits = val[:-1]  # enlever N/S/E/W

    if hemi in ('N', 'S'):
        # Latitude : DDMMSS.ss
        d = int(digits[:2])
        m = int(digits[2:4])
        s = float(digits[4:])
    else:
        # Longitude : DDDMMSS.ss
        d = int(digits[:3])
        m = int(digits[3:5])
        s = float(digits[5:])

    dd = d + m / 60.0 + s / 3600.0
    return -dd if hemi in ('S', 'W') else dd

# ── Parse altitude ────────────────────────────────────────────────
def parse_alt(val_str, uom, code_ref):
    """Retourne l'altitude en pieds."""
    if val_str is None:
        return 0.0
    try:
        val = float(val_str)
    except:
        return 0.0

    uom = (uom or '').upper()
    code_ref = (code_ref or '').upper()

    if uom == 'FL':
        return val * 100.0
    elif uom == 'M':
        return val * 3.28084
    else:  # FT par défaut
        return val

# ── Cercle (pour les zones définies par rayon) ────────────────────
def make_circle(lat_c, lon_c, r_nm, n=48):
    pts = []
    for i in range(n + 1):
        a = math.radians(i * 360.0 / n)
        lat = lat_c + (r_nm / 60.0) * math.cos(a)
        lon = lon_c + (r_nm / 60.0) / math.cos(math.radians(lat_c)) * math.sin(a)
        pts.append([round(lon, 5), round(lat, 5)])
    return pts

# ── Vérification bbox ─────────────────────────────────────────────
def in_bbox(coords):
    if not coords:
        return False
    lons = [c[0] for c in coords]
    lats = [c[1] for c in coords]
    return (max(lons) >= BBOX['lon_min'] and min(lons) <= BBOX['lon_max'] and
            max(lats) >= BBOX['lat_min'] and min(lats) <= BBOX['lat_max'])

# ── Parser principal ──────────────────────────────────────────────
def parse_sia_xml(path):
    print(f"[→] Parsing {path}")
    tree = etree.parse(path)
    root = tree.getroot()

    # ── 1. Lire tous les Ase (espaces aériens) ──────────────────
    ase_dict = {}  # codeId → propriétés

    for ase in root.findall('.//Ase'):
        # Récupérer les champs
        def g(tag):
            el = ase.find(tag)
            return el.text.strip() if el is not None and el.text else None

        code_type     = g('codeType') or ''
        code_id       = g('codeId') or ''
        local_type    = g('txtLocalType') or ''
        name          = g('txtName') or code_id

        # Normaliser le type
        atype = TYPE_MAP.get(code_type.upper())
        if not atype and local_type:
            atype = TYPE_MAP.get(local_type.upper())
        if not atype:
            continue  # type non pertinent pour drones

        # Altitudes
        val_upper  = g('valDistVerUpper')
        uom_upper  = g('uomDistVerUpper')
        code_upper = g('codeDistVerUpper')
        val_lower  = g('valDistVerLower')
        uom_lower  = g('uomDistVerLower')
        code_lower = g('codeDistVerLower')

        upper_ft = parse_alt(val_upper, uom_upper, code_upper)
        lower_ft = parse_alt(val_lower, uom_lower, code_lower)

        # Ignorer les zones entièrement au-dessus de 400 ft
        if lower_ft > DRONE_MAX_FT:
            continue

        ase_dict[code_id] = {
            'id':        code_id,
            'name':      name,
            'type':      atype,
            'lower_ft':  lower_ft,
            'upper_ft':  upper_ft,
            'lower_str': f"{val_lower or 'SFC'} {uom_lower or ''} {code_lower or ''}".strip(),
            'upper_str': f"{val_upper or '?'} {uom_upper or ''} {code_upper or ''}".strip(),
        }

    print(f"[i] {len(ase_dict)} espaces aériens pertinents (≤ {DRONE_MAX_FT} ft)")

    # ── 2. Lire les Abd (géométries) et regrouper par codeId ────
    # Structure : Abd contient AseUid (avec codeId) + des Avx (vertex)
    geo_dict = defaultdict(list)  # codeId → liste de points

    for abd in root.findall('.//Abd'):
        # Récupérer le codeId de l'espace aérien associé
        # Dans le format SIA, Abd contient directement un codeId
        # qui correspond à l'Ase
        code_id_el = abd.find('codeId')
        if code_id_el is None:
            # Parfois imbriqué dans AseUid
            uid = abd.find('.//AseUid')
            if uid is not None:
                code_id_el = uid.find('codeId')

        if code_id_el is None or not code_id_el.text:
            continue

        code_id = code_id_el.text.strip()

        # Ne garder que les Ase qui nous intéressent
        if code_id not in ase_dict:
            continue

        # Lire les points de géométrie (Avx = vertex)
        for avx in abd.findall('.//Avx'):
            lat_el = avx.find('geoLat')
            lon_el = avx.find('geoLong')
            if lat_el is not None and lon_el is not None:
                try:
                    lat = parse_geo(lat_el.text)
                    lon = parse_geo(lon_el.text)
                    geo_dict[code_id].append([round(lon, 5), round(lat, 5)])
                except Exception as e:
                    pass

            # Gestion des arcs (codeType GRC = grand cercle, ABE = arc)
            code_type_el = avx.find('codeType')
            if code_type_el is not None:
                ct = code_type_el.text.strip() if code_type_el.text else ''
                if ct in ('ABE', 'ABN'):
                    # Arc — utiliser centre + rayon si disponible
                    c_lat_el = avx.find('geoLatArc')
                    c_lon_el = avx.find('geoLongArc')
                    r_el     = avx.find('valRadiusArc')
                    if c_lat_el is not None and c_lon_el is not None and r_el is not None:
                        try:
                            c_lat = parse_geo(c_lat_el.text)
                            c_lon = parse_geo(c_lon_el.text)
                            r_nm  = float(r_el.text)
                            # Ajouter quelques points d'arc (approximation)
                            arc_pts = make_circle(c_lat, c_lon, r_nm, n=16)
                            geo_dict[code_id].extend(arc_pts[:8])
                        except:
                            pass

    print(f"[i] Géométries trouvées : {len(geo_dict)} espaces")

    # ── 3. Assembler les features GeoJSON ────────────────────────
    features = []
    stats = defaultdict(int)

    for code_id, ase in ase_dict.items():
        coords = geo_dict.get(code_id, [])
        if len(coords) < 3:
            continue

        # Fermer le polygone
        if coords[0] != coords[-1]:
            coords.append(coords[0])

        # Vérifier bbox
        if not in_bbox(coords):
            continue

        atype = ase['type']
        style = ZONE_TYPES.get(atype, {'color': '#888888', 'opacity': 0.3})

        lo_m = round(ase['lower_ft'] * 0.3048, 1)
        up_m = round(min(ase['upper_ft'], DRONE_MAX_FT) * 0.3048, 1)

        features.append({
            'type': 'Feature',
            'geometry': {'type': 'Polygon', 'coordinates': [coords]},
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

    return features, stats

# ── Export GeoJSON ────────────────────────────────────────────────
def export_geojson(features, output):
    from datetime import datetime
    gj = {
        'type': 'FeatureCollection',
        'metadata': {
            'source':    'SIA DGAC — XML natif',
            'generated': datetime.utcnow().isoformat() + 'Z',
            'drone_max_ft': DRONE_MAX_FT,
            'bbox':      BBOX,
            'count':     len(features),
        },
        'features': features
    }
    with open(output, 'w', encoding='utf-8') as f:
        json.dump(gj, f, ensure_ascii=False, separators=(',', ':'))
    kb = os.path.getsize(output) // 1024
    print(f"[✓] {output} → {len(features)} zones ({kb} Ko)")

# ── Main ──────────────────────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser(description='SIA XML → GeoJSON drones Sud-Ouest')
    ap.add_argument('--input',  '-i', required=True, help='Fichier XML SIA')
    ap.add_argument('--output', '-o', default='airspaces_sudouest_drones.geojson')
    args = ap.parse_args()

    if not os.path.exists(args.input):
        print(f"[!] Fichier introuvable : {args.input}")
        sys.exit(1)

    print("=" * 60)
    print("  SIA Parser v3 — Format XML natif SIA")
    print(f"  Zone : Sud-Ouest France | Limite : {DRONE_MAX_FT} ft / 120 m")
    print("=" * 60)

    features, stats = parse_sia_xml(args.input)
    export_geojson(features, args.output)

    print()
    print(f"[✓] Terminé ! Zones par type :")
    for t, n in sorted(stats.items()):
        label = ZONE_TYPES.get(t, {}).get('label', t)
        print(f"    {t:6s} — {label:20s} : {n}")

if __name__ == '__main__':
    main()
