#!/usr/bin/env python3
"""
SIA AIXM 4.5 Parser v2 — Carte Drones Sud-Ouest France
=======================================================
Dépendances : lxml, requests (stdlib sinon)
Usage :
  1. Télécharger export_xml_bd_SIA2026-xx-xx.zip depuis sia.aviation-civile.gouv.fr
  2. Dézipper → obtenir AIXM4.5_all_FR_OM_2026-xx-xx.xml
  3. python3 sia_parser_v2.py --input AIXM4.5_all_FR_OM_2026-xx-xx.xml
  4. → airspaces_sudouest_drones.geojson

ATTENTION : À titre éducatif. Utiliser uniquement des données officielles à jour
pour toute navigation réelle.
"""
import json, math, re, sys, os
from lxml import etree
from datetime import datetime

# ── Config ───────────────────────────────────────────────────────
BBOX = dict(lon_min=-2.5, lat_min=42.0, lon_max=3.5, lat_max=46.5)
DRONE_MAX_FT = 400   # 400 ft ≈ 122 m

NS = {
    'a': 'http://www.aixm.aero/schema/4.5',
    'g': 'http://www.opengis.net/gml',
}

ZONE_STYLES = {
    'P':    {'label':'Zone Interdite',    'color':'#CC0000','opacity':0.65},
    'R':    {'label':'Zone Réglementée', 'color':'#FF6600','opacity':0.55},
    'D':    {'label':'Zone Dangereuse',  'color':'#FF9900','opacity':0.50},
    'CTR':  {'label':'CTR',              'color':'#0066FF','opacity':0.40},
    'TMA':  {'label':'TMA',              'color':'#0099CC','opacity':0.30},
    'SIV':  {'label':'SIV',              'color':'#009966','opacity':0.28},
    'RTBA': {'label':'RTBA',             'color':'#9900CC','opacity':0.50},
    'ATZ':  {'label':'ATZ',              'color':'#336699','opacity':0.35},
    'RMZ':  {'label':'RMZ',              'color':'#66CCFF','opacity':0.30},
    'TMZ':  {'label':'TMZ',              'color':'#33CC66','opacity':0.30},
    'ZSM':  {'label':'Zone Sensible',    'color':'#FF3399','opacity':0.40},
}

# ── Utilitaires altitude ─────────────────────────────────────────
def parse_alt(val, unit='FT', ref='MSL'):
    if not val: return 0.0
    v = str(val).strip().upper()
    if v in ('SFC','GND','0'):  return 0.0
    if 'UNL' in v or 'UNLIM' in v: return 99999.0
    try:
        num = float(re.sub(r'[^\d.]','',v) or '0')
    except: return 0.0
    unit = str(unit or '').strip().upper()
    if unit == 'M':   num *= 3.28084
    if unit == 'FL':  num *= 100
    return num

# ── Géométrie ────────────────────────────────────────────────────
def parse_poslist(text):
    """Parse une gml:posList 'lat lon lat lon ...' → [(lon,lat),...]"""
    nums = list(map(float, text.split()))
    pts = []
    for i in range(0, len(nums)-1, 2):
        lat, lon = nums[i], nums[i+1]
        pts.append((lon, lat))
    return pts

def bbox_intersects(coords):
    if not coords: return False
    lons = [c[0] for c in coords]
    lats = [c[1] for c in coords]
    return (max(lons) >= BBOX['lon_min'] and min(lons) <= BBOX['lon_max'] and
            max(lats) >= BBOX['lat_min'] and min(lats) <= BBOX['lat_max'])

# ── Parser principal ─────────────────────────────────────────────
def parse_aixm(path):
    print(f'[→] Parsing {path}')
    tree = etree.parse(path)
    root = tree.getroot()

    # Détecter le namespace réel
    tag = root.tag
    ns_url = tag[1:tag.index('}')] if tag.startswith('{') else ''
    NS['a'] = ns_url or NS['a']

    results = []
    total = 0

    for el in root.iter():
        local = el.tag.split('}')[-1] if '}' in el.tag else el.tag
        if local != 'Airspace': continue
        total += 1

        def txt(*names):
            for n in names:
                for ns in [NS['a'], '']:
                    tag = f'{{{NS["a"]}}}{n}' if ns else n
                    found = el.find(f'.//{tag}')
                    if found is not None and found.text:
                        return found.text.strip()
            return ''

        asp_id   = txt('AirspaceId','designator','name') or el.get(f'{{{NS["g"]}}}id','?')
        name     = txt('name','designator') or asp_id
        asp_type = txt('type','AirspaceType').upper()
        cls      = txt('classification','class')

        # Normaliser le type
        matched_type = None
        for t in ZONE_STYLES:
            if asp_type == t or asp_type.startswith(t+'-') or asp_type.startswith(t+' '):
                matched_type = t; break
        if not matched_type: continue

        lower_ft = parse_alt(txt('lowerLimit'), txt('lowerLimitUnit','lowerUnit'), txt('lowerLimitRef','lowerRef'))
        upper_ft = parse_alt(txt('upperLimit'), txt('upperLimitUnit','upperUnit'), txt('upperLimitRef','upperRef'))

        # Ignorer les zones entièrement au-dessus de 400 ft
        if lower_ft > DRONE_MAX_FT: continue

        # Géométrie — chercher posList ou pos
        coords = []
        for pl in el.iter(f'{{{NS["g"]}}}posList'):
            if pl.text and pl.text.strip():
                coords = parse_poslist(pl.text)
                break
        if not coords:
            for pos in el.iter(f'{{{NS["g"]}}}pos'):
                if pos.text:
                    nums = pos.text.split()
                    if len(nums) >= 2:
                        coords.append((float(nums[1]), float(nums[0])))

        if len(coords) < 3: continue
        if not bbox_intersects(coords): continue

        lower_m = round(lower_ft * 0.3048, 1)
        upper_m = round(min(upper_ft, DRONE_MAX_FT) * 0.3048, 1)
        height_m = max(upper_m - lower_m, 5)

        style = ZONE_STYLES[matched_type]
        results.append({
            'id': asp_id, 'name': name,
            'type': matched_type, 'type_label': style['label'],
            'class': cls,
            'lower_ft': lower_ft, 'upper_ft': upper_ft,
            'lower_str': txt('lowerLimit') or 'SFC',
            'upper_str': txt('upperLimit') or '?',
            'lower_m': lower_m, 'upper_m': upper_m, 'height_m': height_m,
            'color': style['color'], 'opacity': style['opacity'],
            'coords': coords,
        })

    print(f'[i] {total} Airspace lus → {len(results)} zones retenues')
    return results

# ── Export GeoJSON ───────────────────────────────────────────────
def to_geojson(zones, out='airspaces_sudouest_drones.geojson'):
    from collections import Counter
    features = []
    for z in zones:
        # Fermer le polygone si nécessaire
        coords = z['coords']
        if coords[0] != coords[-1]: coords = coords + [coords[0]]

        features.append({
            'type': 'Feature',
            'geometry': {'type': 'Polygon', 'coordinates': [coords]},
            'properties': {k: v for k, v in z.items() if k != 'coords'}
        })

    gj = {
        'type': 'FeatureCollection',
        'metadata': {
            'source': 'SIA DGAC — AIXM 4.5',
            'generated': datetime.utcnow().isoformat()+'Z',
            'drone_max_ft': DRONE_MAX_FT,
            'bbox': BBOX,
            'count': len(features),
        },
        'features': features
    }
    with open(out,'w',encoding='utf-8') as f:
        json.dump(gj, f, ensure_ascii=False, separators=(',',':'))

    kb = os.path.getsize(out) / 1024
    print(f'[✓] {out} → {len(features)} zones ({kb:.0f} Ko)')
    counts = Counter(z['type'] for z in zones)
    for t,n in sorted(counts.items()):
        print(f'    {t:6s} {ZONE_STYLES[t]["label"]:25s} {n:3d}')
    return out

# ── Main ─────────────────────────────────────────────────────────
if __name__ == '__main__':
    import argparse
    ap = argparse.ArgumentParser(description='SIA AIXM → GeoJSON drones Sud-Ouest')
    ap.add_argument('--input','-i', default='AIXM4.5_all_FR_OM.xml',
                    help='Fichier AIXM 4.5 du SIA')
    ap.add_argument('--output','-o', default='airspaces_sudouest_drones.geojson')
    args = ap.parse_args()

    if not os.path.exists(args.input):
        print(f'[!] Fichier introuvable : {args.input}')
        print(    '    Télécharger depuis :')
        print(    '    https://www.sia.aviation-civile.gouv.fr/produits-numeriques-en-libre-disposition/les-bases-de-donnees-sia.html')
        sys.exit(1)

    zones = parse_aixm(args.input)
    to_geojson(zones, args.output)
