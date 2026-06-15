#!/usr/bin/env python3
"""
Fetch real polygon boundaries for French PRN zones from OpenStreetMap via Overpass API.
Outputs prn_real_boundaries.geojson with matched zones.
"""

import json, re, unicodedata, sys, warnings
warnings.filterwarnings('ignore')

import requests
from shapely.geometry import shape, mapping, Polygon, LineString
from shapely.ops import unary_union, linemerge, polygonize

OVERPASS_URL = 'https://maps.mail.ru/osm/tools/overpass/api/interpreter'

# ─── Name normalization ────────────────────────────────────────────────────────

def normalize(s):
    """Strip accents, punctuation, OSM suffixes, and common French prefixes."""
    s = s.upper()
    # Remove accents first
    s = unicodedata.normalize('NFKD', s).encode('ASCII', 'ignore').decode()
    # Replace all non-alphanumeric with space
    s = re.sub(r'[^A-Z0-9]+', ' ', s).strip()

    # Strip OSM parenthetical suffixes (aire d'adhésion, cœur, etc.)
    for sfx in [
        ' AIRE D ADHESION', ' AIRE MARITIME ADJACENTE',
        ' AIRE OPTIMUM D ADHESION', ' ZONE COEUR', ' COEUR',
        ' FIER D ARS',  # from LILLEAU DES NIGES (FIER D'ARS)
    ]:
        if s.endswith(sfx):
            s = s[:-len(sfx)].strip()

    # Strip common French protected-area prefixes (order: longest first)
    for pfx in [
        'RESERVE NATURELLE NATIONALE DE LA ',
        'RESERVE NATURELLE NATIONALE DES ',
        'RESERVE NATURELLE NATIONALE DU ',
        'RESERVE NATURELLE NATIONALE DE L ',
        'RESERVE NATURELLE NATIONALE DE ',
        'RESERVE NATURELLE NATIONALE ',
        'RESERVE NATURELLE REGIONALE DE LA ',
        'RESERVE NATURELLE REGIONALE DES ',
        'RESERVE NATURELLE REGIONALE DU ',
        'RESERVE NATURELLE REGIONALE DE ',
        'RESERVE NATURELLE REGIONALE ',
        'RESERVE NATURELLE DE LA ',
        'RESERVE NATURELLE DES ',
        'RESERVE NATURELLE DU ',
        'RESERVE NATURELLE DE L ',
        'RESERVE NATURELLE DE ',
        'RESERVE NATURELLE ',
        'PARC NATIONAL DE LA ',
        'PARC NATIONAL DES ',
        'PARC NATIONAL DU ',
        'PARC NATIONAL DE L ',
        'PARC NATIONAL DE ',
        'PARC NATIONAL ',
        'PARC NATUREL MARIN DE LA ',
        'PARC NATUREL MARIN DES ',
        'PARC NATUREL MARIN D ',
        'PARC NATUREL MARIN DE ',
        'PARC NATUREL MARIN ',
        'RESERVE BIOLOGIQUE DIRIGEE DE ',
        'RESERVE BIOLOGIQUE INTEGRALE DE ',
        'RESERVE BIOLOGIQUE ',
        'FORET DOMANIALE ',
    ]:
        if s.startswith(pfx):
            s = s[len(pfx):]
            break

    return s.strip()

# ─── Load PRN zones ────────────────────────────────────────────────────────────

with open('/Users/simonfaudrit/Desktop/Sky3D/export_xml_bd_sia_2026-06-11-v01/airspaces_france_final.geojson') as f:
    data = json.load(f)

prn_features = {
    f['properties']['name']: f
    for f in data['features']
    if f['properties'].get('type') == 'PRN'
}

# PRN names already start with "PRN "; strip that before normalizing
prn_norm = {normalize(name[4:]): name for name in prn_features}
print(f"PRN zones to match: {len(prn_norm)}", flush=True)

# ─── Query Overpass API ────────────────────────────────────────────────────────

BBOX = '41,-6,52,10'  # France + Corsica bounding box

query = f"""
[out:json][timeout:180][maxsize:268435456];
(
  relation["boundary"="protected_area"]["name"]({BBOX});
  relation["boundary"="national_park"]["name"]({BBOX});
  relation["leisure"="nature_reserve"]["name"]({BBOX});
  way["boundary"="protected_area"]["name"]({BBOX});
  way["boundary"="national_park"]["name"]({BBOX});
  way["leisure"="nature_reserve"]["name"]({BBOX});
);
out geom;
"""

print("Querying Overpass API for French protected areas...", flush=True)
print("(This may take 30-90 seconds)", flush=True)

resp = requests.get(OVERPASS_URL, params={'data': query}, timeout=220)
resp.raise_for_status()
osm_data = resp.json()
print(f"Got {len(osm_data['elements'])} OSM elements", flush=True)

# ─── Convert OSM elements to GeoJSON geometries ───────────────────────────────

def way_to_coords(geom_list):
    """Convert Overpass way geometry to list of [lon, lat] coords (NOT closed)."""
    return [[pt['lon'], pt['lat']] for pt in geom_list]

def assemble_rings(way_coord_lists):
    """
    Properly assemble OSM way segments into closed rings using linemerge+polygonize.
    OSM multipolygon outer/inner ways are open segments that chain together.
    Treating each way as a closed ring creates sliver-polygons.
    """
    lines = []
    for coords in way_coord_lists:
        if len(coords) >= 2:
            lines.append(LineString(coords))
    if not lines:
        return []
    merged = linemerge(lines)
    polys = list(polygonize(merged))
    return polys

def element_to_geometry(el):
    if el['type'] == 'way':
        coords = way_to_coords(el.get('geometry', []))
        if len(coords) < 3:
            return None
        # Single way: close it if needed
        if coords[0] != coords[-1]:
            coords.append(coords[0])
        try:
            return json.loads(json.dumps(mapping(Polygon(coords).buffer(0))))
        except Exception:
            return None

    elif el['type'] == 'relation':
        outer_coords, inner_coords = [], []
        for m in el.get('members', []):
            if m.get('type') != 'way' or 'geometry' not in m:
                continue
            coords = way_to_coords(m['geometry'])
            if len(coords) < 2:
                continue
            if m.get('role') == 'outer':
                outer_coords.append(coords)
            elif m.get('role') == 'inner':
                inner_coords.append(coords)

        if not outer_coords:
            return None

        try:
            outer_polys = assemble_rings(outer_coords)
            inner_polys = assemble_rings(inner_coords) if inner_coords else []

            if not outer_polys:
                return None

            # Subtract holes from outer polygons
            result_polys = []
            for outer in outer_polys:
                outer = outer.buffer(0)
                for hole in inner_polys:
                    hole = hole.buffer(0)
                    if outer.intersects(hole):
                        outer = outer.difference(hole)
                result_polys.append(outer)

            merged = unary_union(result_polys).buffer(0)
            return json.loads(json.dumps(mapping(merged)))
        except Exception as e:
            # Fallback: assemble rings naively (old method)
            try:
                polys = []
                for coords in outer_coords:
                    if coords[0] != coords[-1]:
                        coords = coords + [coords[0]]
                    if len(coords) >= 4:
                        polys.append(Polygon(coords).buffer(0))
                if polys:
                    return json.loads(json.dumps(mapping(unary_union(polys).buffer(0))))
            except Exception:
                pass
            return None

    return None

# ─── Build normalized name → (geometry, area) index ──────────────────────────

osm_index = {}  # norm_name → (geometry, area_deg2)

for el in osm_data['elements']:
    name = el.get('tags', {}).get('name', '')
    if not name:
        continue
    geom = element_to_geometry(el)
    if geom is None:
        continue
    try:
        area = shape(geom).area
    except Exception:
        area = 0.0
    norm = normalize(name)
    if norm not in osm_index or area > osm_index[norm][1]:
        osm_index[norm] = (geom, area)

print(f"OSM index: {len(osm_index)} unique normalized names", flush=True)

# ─── Fetch specific national park relations by OSM ID ─────────────────────────
# Some parks either fail geometry processing or have name mismatches in the bulk query.
# OSM relation IDs sourced from the OSM website for French national parks.
MANUAL_RELATION_IDS = {
    # PRN name → OSM relation ID
    'PRN PARC NATIONAL DES ECRINS':                    1024498,
    'PRN PARC NATIONAL DES PYRENEES OCCIDENTALES':    14599244,
    'PRN PARC NATIONAL DE LA VANOISE':                 1024500,
    'PRN PARC NATIONAL DES CEVENNES':                  1024504,
    'PRN PARC NATIONAL DU MERCANTOUR':                 1024510,
    'PRN CALANQUES':                                   3080198,
    'PRN PARC NATIONAL DE PORT CROS':                  9815334,
    'PRN PARC NATIONAL DE FORETS':                    10304087,
    'PRN BONIFACIO':                                   9408527,
    # Additional reserves identified by manual OSM search
    'PRN CHAUDEFOUR':                                  1023765,  # "vallée de Chaudefour"
    'PRN GROTTE ET PELOUSES D\'ACQUIN-WESTBECOURT':   1066663,  # combined reserve
    'PRN COTEAUX DE WAVRANS-SUR-L\'AA':               1066663,  # same combined reserve
    'PRN PLATEAU DES CERBICALES':                     14306326,  # "îles Cerbicale"
}

rel_ids = list(set(MANUAL_RELATION_IDS.values()))  # deduplicate
id_query = f'[out:json][timeout:120]; relation(id:{",".join(str(i) for i in rel_ids)}); out geom;'
print(f"Fetching {len(rel_ids)} relations by ID...", flush=True)
resp2 = requests.get(OVERPASS_URL, params={'data': id_query}, timeout=150)
resp2.raise_for_status()
manual_data = resp2.json()

# Multiple PRN zones may share the same relation ID
id_to_geom = {}
for el in manual_data['elements']:
    geom = element_to_geometry(el)
    if geom:
        id_to_geom[el['id']] = geom

manual_matched = {}
for prn_name, rel_id in MANUAL_RELATION_IDS.items():
    if rel_id in id_to_geom:
        manual_matched[prn_name] = id_to_geom[rel_id]
        print(f"  Fetched by ID: '{prn_name}' (rel {rel_id})", flush=True)
    else:
        print(f"  WARNING: geometry failed for '{prn_name}' (rel {rel_id})", flush=True)

# Add manual results to OSM index (keyed by exact PRN name)
for prn_name, geom in manual_matched.items():
    norm = normalize(prn_name[4:])  # strip 'PRN '
    try:
        area = shape(geom).area
    except Exception:
        area = 1.0
    if norm not in osm_index or area > osm_index[norm][1]:
        osm_index[norm] = (geom, area)
    # Also index under 'PYRENEES OCCIDENTALES' for the Pyrénées park (OSM name = 'PYRENEES')
    if norm == 'PYRENEES':
        osm_index['PYRENEES OCCIDENTALES'] = (geom, area)

print(f"OSM index after manual additions: {len(osm_index)} entries", flush=True)

# ─── Exact match pass ─────────────────────────────────────────────────────────

matched = {}
unmatched = list(prn_norm.keys())

for norm_prn in list(unmatched):
    if norm_prn in osm_index:
        matched[prn_norm[norm_prn]] = osm_index[norm_prn][0]
        unmatched.remove(norm_prn)

print(f"Exact match: {len(matched)}/{len(prn_norm)}", flush=True)

# ─── Fuzzy pass: containment matching ────────────────────────────────────────

all_osm_norms = list(osm_index.keys())
still_unmatched = []

for norm_prn in unmatched:
    full_name = prn_norm[norm_prn]
    best_norm, best_score = None, 0

    for osm_norm in all_osm_norms:
        # One must fully contain the other (word-aligned)
        if norm_prn in osm_norm or osm_norm in norm_prn:
            score = min(len(norm_prn), len(osm_norm)) / max(len(norm_prn), len(osm_norm))
            if score > best_score and score >= 0.70:
                best_score, best_norm = score, osm_norm

    if best_norm:
        matched[full_name] = osm_index[best_norm][0]
        print(f"  Fuzzy: '{full_name}' → '{best_norm}' (score={best_score:.2f})", flush=True)
    else:
        still_unmatched.append(full_name)

print(f"\nFinal: matched={len(matched)}, unmatched={len(still_unmatched)}", flush=True)

if still_unmatched:
    print("\nZones keeping circle approximation:", flush=True)
    for n in sorted(still_unmatched):
        print(f"  - {n}", flush=True)

# ─── Simplify geometries ──────────────────────────────────────────────────────
# Tolerance ~0.001° ≈ 100m — adequate for aeronautical display, reduces file size ~10x

SIMPLIFY_TOLERANCE = 0.0002  # degrees (~22m) — preserves shape, manageable size

def simplify_geometry(geom_dict):
    """Simplify a GeoJSON geometry using Shapely."""
    try:
        shp = shape(geom_dict)
        simplified = shp.simplify(SIMPLIFY_TOLERANCE, preserve_topology=True)
        return json.loads(json.dumps(mapping(simplified)))
    except Exception:
        return geom_dict

# ─── Build output GeoJSON ─────────────────────────────────────────────────────

output_features = []
for prn_name, prn_feat in prn_features.items():
    props = dict(prn_feat['properties'])
    if prn_name in matched:
        geom = simplify_geometry(matched[prn_name])
        props['geometry_source'] = 'osm'
    else:
        geom = prn_feat['geometry']
        props['geometry_source'] = 'circle_approx'
    output_features.append({'type': 'Feature', 'geometry': geom, 'properties': props})

output = {'type': 'FeatureCollection', 'features': output_features}

out_path = '/Users/simonfaudrit/Desktop/Sky3D/export_xml_bd_sia_2026-06-11-v01/prn_real_boundaries.geojson'
with open(out_path, 'w') as f:
    json.dump(output, f, ensure_ascii=False)

osm_count = sum(1 for ft in output_features if ft['properties']['geometry_source'] == 'osm')
circle_count = len(output_features) - osm_count
print(f"\nSaved {out_path}", flush=True)
print(f"  {osm_count} real OSM boundaries", flush=True)
print(f"  {circle_count} circle approximations", flush=True)
