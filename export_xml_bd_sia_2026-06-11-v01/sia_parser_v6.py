#!/usr/bin/env python3
"""
SIA Parser v6 — XML_SIA natif DGAC (géométrie + altitude)
Source   : XML_SIA_2026-06-11.xml (AIRAC 06/2026)
Couverture : France métropolitaine [LF]
Géométrie : points pré-calculés par le SIA (précis, pas de ré-interpolation)
Altitude  : Volume → Plafond/Plancher/PlafondRefUnite/PlancherRefUnite
Cercles   : PJE (3NM), SUR/ZICAD (1NM), cir(...) extrait du Contour

Usage:
    cd export_xml_bd_sia_2026-06-11-v01
    python3 sia_parser_v6.py --input XML_SIA_2026-06-11.xml
"""
import json, math, re, sys, os, argparse
from xml.etree import ElementTree as ET
from collections import defaultdict
from datetime import datetime

# ── Mapping TypeEspace → type interne ─────────────────────────────
TYPE_MAP = {
    'P':       'P',
    'R':       'R',
    'D':       'D',
    'CTR':     'CTR',
    'TMA':     'TMA',
    'CTA':     'CTA',
    'SIV':     'SIV',
    'FBZ':     'CTR',    # French Base Zone → CTR
    'RMZ':     'RMZ',
    'RMZ-TMZ': 'RMZ',
    'TMZ':     'TMZ',
    'TRA':     'TRA',
    'TrVL':    'TRA',
    'TrPla':   'TRA',
    'TrPVL':   'TRA',
    'Vol':     None,      # vol libre (circuits aérodrome) ≠ zones VOLTAC géographiques
    'Pje':     'PJE',
    'PRN':     'PRN',
    'SUR':     'SUR',    # Zone Sûreté = ZICAD
    # Ignorés
    'Aer':     None,     # aérodrome (pas un espace aérien)
    'CTL':     None,     # contrôle générique
    'AP':      None,
    'FIR':     None,
    'FRA':     None,
    'UIR':     None,
    'UTA':     None,
    'UAC':     None,
    'ACC':     None,
    'Bal':     None,
    'LTA':     None,
    'OCA':     None,
    'CBA':     None,
    'other':   None,
    '':        None,
}

# ── Styles d'affichage ────────────────────────────────────────────
ZONE_STYLES = {
    'P':      {'label': 'Zone Interdite (P)',    'color': '#D20000', 'opacity': 0.70},
    'R':      {'label': 'Zone Réglementée (R)', 'color': '#D20000', 'opacity': 0.55},
    'D':      {'label': 'Zone Dangereuse (D)',  'color': '#D20000', 'opacity': 0.48},
    'CTR':    {'label': 'CTR',                  'color': '#1a6bff', 'opacity': 0.40},
    'TMA':    {'label': 'TMA',                  'color': '#0090bb', 'opacity': 0.28},
    'CTA':    {'label': 'CTA',                  'color': '#0066aa', 'opacity': 0.22},
    'SIV':    {'label': 'SIV',                  'color': '#00aa66', 'opacity': 0.22},
    'RMZ':    {'label': 'RMZ',                  'color': '#44aadd', 'opacity': 0.35},
    'TMZ':    {'label': 'TMZ',                  'color': '#33cc66', 'opacity': 0.30},
    'VOLTAC': {'label': 'VOLTAC',               'color': '#FF6600', 'opacity': 0.45},
    'PJE':    {'label': 'Zone Para (PJE)',       'color': '#cc6600', 'opacity': 0.40},
    'PRN':    {'label': 'Parc Naturel (PRN)',   'color': '#006633', 'opacity': 0.30},
    'TRA':    {'label': 'Zone Transit (TRA)',   'color': '#884400', 'opacity': 0.35},
    'SUR':    {'label': 'Zone Sûreté (SUR)',    'color': '#8800cc', 'opacity': 0.55},
}

# Rayon par défaut (NM) pour les zones sans polygone
DEFAULT_RADIUS_NM = {
    'PJE':    3.0,
    'SUR':    1.0,
    'PRN':    2.0,
    'VOLTAC': 5.0,
}

# France métropolitaine bbox
METRO_BBOX = dict(lon_min=-6.0, lat_min=41.0, lon_max=10.0, lat_max=51.5)

# ── Géométrie ─────────────────────────────────────────────────────

def circle_polygon(lat, lon, radius_nm, n=72):
    """Polygone approximant un cercle (lat,lon en degrés décimaux)."""
    r_lat = radius_nm / 60.0
    r_lon = radius_nm / 60.0 / math.cos(math.radians(lat))
    pts = []
    for i in range(n):
        a = math.radians(360.0 * i / n)
        pts.append([round(lon + r_lon * math.sin(a), 6),
                    round(lat + r_lat * math.cos(a), 6)])
    pts.append(pts[0])
    return pts

def extract_circle_from_contour(contour_text):
    """
    Extrait centre + rayon depuis le champ Contour.
    Format : "...,cir(lat lon:radius:unit:...)"
    Retourne (lat, lon, radius_nm) ou None.
    """
    m = re.search(r'cir\(\s*([-\d.]+)\s+([-\d.]+)\s*:\s*([\d.]+)\s*:\s*(\w+)', contour_text or '')
    if not m:
        return None
    c_lat, c_lon = float(m.group(1)), float(m.group(2))
    radius, unit = float(m.group(3)), m.group(4).upper()
    if unit == 'KM':   radius /= 1.852
    elif unit == 'M':  radius /= 1852.0
    return c_lat, c_lon, radius

def parse_geometrie(geo_text, contour_text='', atype=''):
    """
    Parse le champ Geometrie (lat,lon décimaux, une paire par ligne).
    - Si >= 3 points : polygone direct.
    - Si 1 point ou 0 mais Contour cir() : cercle calculé.
    - Si 1 point seulement : cercle avec rayon par défaut du type.
    Retourne [[lon,lat], ...] fermé, ou None.
    """
    pts = []
    if geo_text:
        for line in geo_text.strip().split('\n'):
            line = line.strip()
            if not line:
                continue
            parts = re.split(r'[,\s]+', line, 1)
            if len(parts) >= 2:
                try:
                    lat = float(parts[0])
                    lon = float(parts[1])
                    # Filtrer les points aberrants (hors Terre)
                    if -90 <= lat <= 90 and -180 <= lon <= 180:
                        pts.append([round(lon, 6), round(lat, 6)])
                except ValueError:
                    pass

    # Dédupliquer les points consécutifs quasi-identiques
    clean = [pts[0]] if pts else []
    for p in pts[1:]:
        prev = clean[-1]
        dx, dy = p[0] - prev[0], p[1] - prev[1]
        if dx*dx + dy*dy > 1e-10:
            clean.append(p)
    pts = clean

    if len(pts) >= 3:
        if pts[0] != pts[-1]:
            pts.append(pts[0])
        return pts

    # Tentative cercle depuis Contour
    cir = extract_circle_from_contour(contour_text)
    if cir:
        c_lat, c_lon, radius_nm = cir
        return circle_polygon(c_lat, c_lon, radius_nm)

    # Point unique → cercle par défaut selon le type
    if len(pts) == 1 and atype in DEFAULT_RADIUS_NM:
        lon0, lat0 = pts[0]
        return circle_polygon(lat0, lon0, DEFAULT_RADIUS_NM[atype])

    return None

def in_metro_france(coords):
    if not coords:
        return False
    lons = [c[0] for c in coords]
    lats = [c[1] for c in coords]
    return (max(lons) >= METRO_BBOX['lon_min'] and
            min(lons) <= METRO_BBOX['lon_max'] and
            max(lats) >= METRO_BBOX['lat_min'] and
            min(lats) <= METRO_BBOX['lat_max'])

# ── Altitude ──────────────────────────────────────────────────────

def parse_alt_ft(val_str, ref_unite):
    """Convertit une altitude XML_SIA en pieds."""
    try:
        val = float(val_str or '0')
    except ValueError:
        val = 0.0
    ref = (ref_unite or '').strip().upper()
    if ref == 'FL':       return val * 100.0
    if ref in ('FT AMSL', 'FT AMSL', 'FT'):  return val
    if ref == 'SFC':      return 0.0
    if ref == 'M':        return val * 3.28084
    return val

ALT_DEFAULTS = {
    'P':      (0,  9999),
    'R':      (0,  9999),
    'D':      (0,  4000),
    'CTR':    (0,  2500),
    'TMA':    (1500, 9500),
    'CTA':    (4000, 19500),
    'SIV':    (0,  9500),
    'VOLTAC': (0,  1000),
    'PJE':    (0,  3000),
    'PRN':    (0,  1000),
    'SUR':    (0,   500),
    'RMZ':    (0,  2500),
    'TMZ':    (0,  9500),
    'TRA':    (0,  9500),
}

# ── Parsing principal ──────────────────────────────────────────────

def tv(el, tag):
    """Text value d'un sous-élément, vide si absent."""
    f = el.find(tag)
    return (f.text or '').strip() if f is not None else ''

def build_name(lk, type_raw, nom, nom_usuel):
    """
    Construit le nom d'affichage d'une zone.
    - CTR/TMA/CTA/R/P/D : depuis le lk "[LF][TYPE NAME]" → "TYPE NAME"
    - Vol/Pje/PRN/SUR   : prefer NomUsuel (plus lisible que "Vol 6158")
    """
    lk_match = re.search(r'\[LF\]\[(.+?)\]', lk)
    lk_name = lk_match.group(1) if lk_match else f"{type_raw} {nom}".strip()

    # Pour les types à code numérique, préférer NomUsuel
    if type_raw in ('Vol', 'Pje', 'PRN', 'SUR') and nom_usuel:
        prefix = {'Vol': 'VOLTAC', 'Pje': 'PJE', 'PRN': 'PRN', 'SUR': 'SUR'}.get(type_raw, type_raw)
        return f"{prefix} {nom_usuel}"

    return lk_name

def parse_xml_sia(path):
    print(f"[→] Parsing {path} ...")
    tree = ET.parse(path)
    root = tree.getroot()

    # ── Index 1 : Espace pk → métadonnées ─────────────────────────
    esp_by_pk = {}
    for esp in root.findall('.//Espace'):
        pk  = esp.get('pk')
        lk  = esp.get('lk', '')
        if not pk or '[LF]' not in lk:
            continue                      # uniquement France métropolitaine
        type_raw = tv(esp, 'TypeEspace')
        atype = TYPE_MAP.get(type_raw)
        if atype is None:
            continue
        esp_by_pk[pk] = {
            'pk':       pk,
            'type_raw': type_raw,
            'type':     atype,
            'nom':      tv(esp, 'Nom'),
            'lk':       lk,
        }

    print(f"[i] {len(esp_by_pk)} Espaces [LF] pertinents")

    # ── Index 2 : Espace pk → liste de Parties ────────────────────
    parts_by_esp = defaultdict(list)
    for partie in root.findall('.//Partie'):
        ref = partie.find('Espace')
        if ref is None:
            continue
        esp_pk = ref.get('pk')
        if esp_pk in esp_by_pk:
            parts_by_esp[esp_pk].append(partie)

    # ── Index 3 : Partie pk → Volume (altitude) ───────────────────
    vol_by_partie = defaultdict(list)
    for vol in root.findall('.//Volume'):
        ref = vol.find('Partie')
        if ref is None:
            continue
        vol_by_partie[ref.get('pk')].append(vol)

    # ── Génération des features GeoJSON ───────────────────────────
    features = []
    stats    = defaultdict(int)
    skip_geo = 0
    skip_box = 0

    for esp_pk, esp in esp_by_pk.items():
        atype    = esp['type']
        type_raw = esp['type_raw']
        parties  = parts_by_esp.get(esp_pk, [])

        if not parties:
            skip_geo += 1
            continue

        # Utiliser la première Partie (géométrie principale)
        # Pour les zones multi-secteurs, chaque Partie = un secteur distinct
        for partie in parties:
            partie_pk   = partie.get('pk', '')
            geo_text    = tv(partie, 'Geometrie')
            contour_txt = tv(partie, 'Contour')
            nom_usuel   = tv(partie, 'NomUsuel')
            nom_partie  = tv(partie, 'NomPartie')
            num_partie  = tv(partie, 'NumeroPartie')

            coords = parse_geometrie(geo_text, contour_txt, atype)
            if not coords or len(coords) < 4:
                skip_geo += 1
                continue

            if not in_metro_france(coords):
                skip_box += 1
                continue

            # Nom d'affichage
            name = build_name(esp['lk'], type_raw, esp['nom'], nom_usuel)
            # Si multi-secteurs avec NomPartie non vide, l'ajouter
            if nom_partie and nom_partie != '.' and len(parties) > 1:
                name = f"{name} ({nom_partie})"

            # Altitude depuis Volume
            vols = vol_by_partie.get(partie_pk, [])
            if vols:
                v = vols[0]
                lower_ft  = parse_alt_ft(tv(v, 'Plancher'),  tv(v, 'PlancherRefUnite'))
                upper_ft  = parse_alt_ft(tv(v, 'Plafond'),   tv(v, 'PlafondRefUnite'))
                lower_str = f"{tv(v,'Plancher') or 'SFC'} {tv(v,'PlancherRefUnite')}".strip()
                upper_str = f"{tv(v,'Plafond') or '?'} {tv(v,'PlafondRefUnite')}".strip()
            else:
                lo, hi = ALT_DEFAULTS.get(atype, (0, 9999))
                lower_ft, upper_ft = float(lo), float(hi)
                lower_str = f"{lo} ft"
                upper_str = f"{hi} ft"

            lower_m = round(lower_ft * 0.3048, 1)
            upper_m = round(upper_ft * 0.3048, 1)
            style   = ZONE_STYLES.get(atype, {'label': atype, 'color': '#888888', 'opacity': 0.3})

            features.append({
                'type': 'Feature',
                'geometry': {'type': 'Polygon', 'coordinates': [coords]},
                'properties': {
                    'id':         f"{esp_pk}_{partie_pk}",
                    'name':       name,
                    'type':       atype,
                    'type_label': style['label'],
                    'class':      '',
                    'lower_ft':   lower_ft,
                    'upper_ft':   upper_ft,
                    'lower_str':  lower_str,
                    'upper_str':  upper_str,
                    'lower_m':    lower_m,
                    'upper_m':    max(upper_m, 5),
                    'height_m':   max(upper_m - lower_m, 5),
                    'color':      style['color'],
                    'opacity':    style['opacity'],
                    'source':     'XML_SIA_2026-06-11',
                }
            })
            stats[atype] += 1

    print(f"[i] {skip_geo} Parties sans géométrie valide (ignorées)")
    print(f"[i] {skip_box} Parties hors France métropolitaine (ignorées)")
    return features, stats

# ── Export ────────────────────────────────────────────────────────

def export_geojson(features, output):
    gj = {
        'type': 'FeatureCollection',
        'metadata': {
            'source':    'DGAC SIA — XML_SIA AIRAC 06/2026',
            'generated': datetime.utcnow().isoformat() + 'Z',
            'count':     len(features),
        },
        'features': features,
    }
    with open(output, 'w', encoding='utf-8') as f:
        json.dump(gj, f, ensure_ascii=False, separators=(',', ':'))
    kb = os.path.getsize(output) // 1024
    print(f"[✓] {output} → {len(features)} zones ({kb} Ko)")

def main():
    ap = argparse.ArgumentParser(description='XML_SIA → GeoJSON espaces aériens France')
    ap.add_argument('--input',  '-i', default='XML_SIA_2026-06-11.xml')
    ap.add_argument('--output', '-o', default='airspaces_france_v6.geojson')
    args = ap.parse_args()

    if not os.path.exists(args.input):
        print(f"[!] Fichier introuvable : {args.input}")
        sys.exit(1)

    print("=" * 60)
    print("  SIA Parser v6 — XML_SIA natif DGAC")
    print(f"  Source : {args.input}")
    print("=" * 60)

    features, stats = parse_xml_sia(args.input)
    export_geojson(features, args.output)

    total = sum(stats.values())
    print(f"\n[✓] {total} zones générées — détail :")
    for tp, n in sorted(stats.items(), key=lambda x: -x[1]):
        label = ZONE_STYLES.get(tp, {}).get('label', tp)
        print(f"    {tp:8s} — {label:30s} : {n}")

if __name__ == '__main__':
    main()
