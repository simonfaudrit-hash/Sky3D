#!/usr/bin/env python3
"""
Génère les zones de restriction de hauteur "vol au voisinage des aérodromes"
(Guide DSAC Catégorie Spécifique, Annexe 4) autour :
  - des pistes d'aérodromes / hélistations (AIXM)
  - des plateformes ULM (basulm.csv)

Modèle (paliers = distance max → hauteur max, m) :
  A4.1 piste <1200m sans IFR : 500→0(interdit), 3500→50, 5000→100
  A4.2 piste >=1200m ou IFR  : 2500→30, 5000→60, 8000→100, 10000→120
  A4.3 hélistation (cercles) : 1000→50, 2500→100, 3500→120
  A4.4 plateforme ULM        : 500→30, 1500→100, 2500→120

Sortie : ad_restrictions.geojson (anneaux par palier, hauteur + couleur).
"""
import re, json, csv, math, xml.etree.ElementTree as ET
from shapely.geometry import LineString, Point, mapping
from shapely.ops import transform

BASE = '/Users/simonfaudrit/Desktop/Sky3D'
AIXM = f'{BASE}/export_xml_bd_sia_2026-06-11-v01/AIXM4.5_all_FR_OM_2026-06-11.xml'
CSV  = f'{BASE}/basulm.csv'
OUT  = f'{BASE}/export_xml_bd_sia_2026-06-11-v01/ad_restrictions.geojson'

# Paliers (rayon ext. m, hauteur m ; hauteur -1 = interdit) ────────────────
TIERS = {
    'A4.1': [(500, -1), (3500, 50), (5000, 100)],
    'A4.2': [(2500, 30), (5000, 60), (8000, 100), (10000, 120)],
    'A4.3': [(1000, 50), (2500, 100), (3500, 120)],
    'A4.4': [(500, 30), (1500, 100), (2500, 120)],
}
COLOR = {-1: '#7a0010', 30: '#e01010', 50: '#e84d10', 60: '#f07810',
         100: '#f0a810', 120: '#6fbf3f'}

def dms(s):
    s = s.strip(); h = s[-1]; s = s[:-1]
    if h in 'NS': dd, mm, ss = float(s[0:2]), float(s[2:4]), float(s[4:])
    else:         dd, mm, ss = float(s[0:3]), float(s[3:5]), float(s[5:])
    v = dd + mm/60 + ss/3600
    return -v if h in 'SW' else v

# ─── Projection locale (équirectangulaire métrique) ──────────────────────────
def projector(lat0, lon0):
    k = math.cos(math.radians(lat0))
    fwd = lambda lon, lat: ((lon-lon0)*111320*k, (lat-lat0)*110540)
    inv = lambda x, y: (lon0 + x/(111320*k), lat0 + y/110540)
    return fwd, inv

def make_rings(geom_lonlat, tiers, lat0, lon0, quad=6):
    """geom_lonlat : LineString (piste) ou Point (hélistation). Retourne [(héch, polygon_lonlat)]."""
    fwd, inv = projector(lat0, lon0)
    g = transform(lambda xs, ys: fwd(xs, ys) if False else None, geom_lonlat) if False else None
    # transform manuel (shapely.ops.transform passe des séquences)
    def tf(x, y, z=None):
        # x,y are arrays/scalars of lon,lat
        import numpy as _n
        pass
    # plus simple : reprojeter les coords à la main
    if geom_lonlat.geom_type == 'LineString':
        pts = [fwd(x, y) for x, y in geom_lonlat.coords]
        gm = LineString(pts)
    else:
        x, y = fwd(geom_lonlat.x, geom_lonlat.y); gm = Point(x, y)
    rings = []
    prev = None
    for r, h in tiers:
        outer = gm.buffer(r, quad_segs=quad)
        ring = outer if prev is None else outer.difference(prev)
        prev = outer
        ring = ring.simplify(40)
        if ring.is_empty: continue
        # reprojeter en lon/lat
        def back(geom):
            if geom.geom_type == 'Polygon':
                ext = [list(inv(x, y)) for x, y in geom.exterior.coords]
                holes = [[list(inv(x, y)) for x, y in r.coords] for r in geom.interiors]
                return {'type': 'Polygon', 'coordinates': [ext] + holes}
            else:
                return {'type': 'MultiPolygon',
                        'coordinates': [[[list(inv(x, y)) for x, y in p.exterior.coords]]
                                        + [[list(inv(x, y)) for x, y in r.coords] for r in p.interiors]
                                        for p in geom.geoms]}
        rings.append((h, back(ring)))
    return rings

# ─── 1) Aérodromes / pistes depuis AIXM ──────────────────────────────────────
ahps = {}        # codeId -> {name, lat, lon, elev}
rwys = {}        # (codeId, desig) -> valLen
rdns = {}        # (codeId, rwy_desig) -> [ (lat,lon), ... ] (seuils)

for ev, el in ET.iterparse(AIXM, events=('end',)):
    if el.tag == 'Ahp':
        u = el.find('AhpUid'); cid = u.find('codeId').text if u.find('codeId') is not None else None
        la = el.find('geoLat'); lo = el.find('geoLong'); nm = el.find('txtName')
        ev_ = el.find('valElev')
        ref = el.find('txtDescrRefPt')
        # Ignorer les « aéroports fictifs » AFS (FIC/ACC/COM/NOF/CROSS/camps) : pas
        # de piste réelle, tous au même point placeholder (44°59'23"N 008°32'23"W,
        # en plein Atlantique) → sinon faux axes de piste en mer.
        fictive = ref is not None and ref.text and 'fictive' in ref.text.lower()
        if cid and la is not None and lo is not None and not fictive:
            ahps[cid] = {'name': nm.text if nm is not None else cid,
                         'lat': dms(la.text), 'lon': dms(lo.text),
                         'elev': float(ev_.text) if ev_ is not None and ev_.text else 0}
        el.clear()
    elif el.tag == 'Rwy':
        u = el.find('RwyUid'); cid = u.find('AhpUid/codeId'); des = u.find('txtDesig')
        ln = el.find('valLen')
        if cid is not None and des is not None and ln is not None:
            try: rwys[(cid.text, des.text)] = float(ln.text)
            except: pass
        el.clear()
    elif el.tag == 'Rdn':
        u = el.find('RdnUid'); cid = u.find('RwyUid/AhpUid/codeId'); rdes = u.find('RwyUid/txtDesig')
        la = el.find('geoLat'); lo = el.find('geoLong')
        if cid is not None and rdes is not None and la is not None and lo is not None:
            rdns.setdefault((cid.text, rdes.text), []).append((dms(la.text), dms(lo.text)))
        el.clear()

# Sortie COMPACTE : sources (segment/point + catégorie). Les anneaux sont
# générés côté client (JS) au chargement → fichier léger.
srcs = []
def add(name, cat, geom, lat0, lon0, ref_elev, src):
    if geom.geom_type == 'LineString':
        g = [[round(x, 5), round(y, 5)] for x, y in geom.coords]
    else:
        g = [[round(geom.x, 5), round(geom.y, 5)]]
    srcs.append({'n': name, 'c': cat, 'e': round(ref_elev), 'g': g})

# Segment de piste depuis centre + orientation (°) + longueur (m)
def seg_from(lat, lon, brg, ln):
    fwd, inv = projector(lat, lon)
    half = ln / 2; th = math.radians(brg)
    dx, dy = math.sin(th)*half, math.cos(th)*half
    return LineString([inv(-dx, -dy), inv(dx, dy)])
def parse_brg(desig):
    m = re.match(r'(\d{1,2})', desig or '')
    return int(m.group(1)) * 10 if m else None
def near(lat, lon, coords, km=1.5):
    kc = math.cos(math.radians(lat))
    return any(abs(la-lat) < 0.02 and math.hypot((lo-lon)*kc, la-lat)*111 < km for la, lo in coords)

n_ad = n_heli = n_ulm = 0
rwy_ad_coords = []   # aérodromes AVEC vraie piste (pour dédup ULM)
no_rwy_ads = []      # (cid, a) sans piste → décision cercle après lecture ULM
for cid, a in ahps.items():
    my_rwys = [(d, ln) for (c, d), ln in rwys.items() if c == cid]
    runway_segs = []
    for d, ln in my_rwys:
        ths = rdns.get((cid, d))
        if ths and len(ths) >= 2:                       # seuils Rdn précis
            seg = LineString([(ths[0][1], ths[0][0]), (ths[1][1], ths[1][0])])
        else:                                            # repli : ARP + orientation(désig) + longueur
            brg = parse_brg(d)
            if brg is None or not ln: continue
            seg = seg_from(a['lat'], a['lon'], brg, ln)
        runway_segs.append((seg, ln))
    if runway_segs:
        for seg, ln in runway_segs:
            add(f"{a['name']} ({cid})", 'A4.2' if ln >= 1200 else 'A4.1', seg, a['lat'], a['lon'], a['elev'], 'AIXM')
        rwy_ad_coords.append((a['lat'], a['lon'])); n_ad += 1
    else:
        no_rwy_ads.append((cid, a))   # piste inconnue dans l'AIXM → voir ULM, sinon cercle

# ─── 2) Plateformes ULM depuis basulm.csv ────────────────────────────────────
rows = list(csv.reader(open(CSV, encoding='latin-1'), delimiter=';'))
hdr = rows[0]
def ci(name):
    for i, h in enumerate(hdr):
        if name.lower() in h.lower(): return i
    return -1
iPos, iOri, iLen, iTopo, iObs = ci('Position'), ci('Orientation premi'), ci('Longueur premi'), ci('Toponyme'), ci('Obsol')
iAlt = ci('Altitude')
ulm_list = []   # (lat, lon, seg, alt, name)
for r in rows[1:]:
    if len(r) <= max(iPos, iOri, iLen): continue
    if r[iObs].strip(): continue
    pos = r[iPos].strip()
    if ',' not in pos: continue
    try: lat, lon = [float(x) for x in pos.split(',')]
    except: continue
    if not (-90 <= lat <= 90 and -180 <= lon <= 180): continue
    brg = parse_brg(re.sub(r"[^0-9-]", '', r[iOri]))
    try: ln = float(re.sub(r'[^0-9.]', '', r[iLen]) or 0)
    except: ln = 0
    seg = seg_from(lat, lon, brg, ln) if (brg is not None and ln > 0) else Point(lon, lat)
    try: alt = float(re.sub(r'[^0-9.]', '', r[iAlt]) or 0) if iAlt >= 0 and len(r) > iAlt else 0
    except: alt = 0
    ulm_list.append((lat, lon, seg, alt, r[iTopo].strip() or 'ULM'))

# ULM : on ignore celles co-localisées avec un aérodrome ayant une VRAIE piste (doublon)
for lat, lon, seg, alt, name in ulm_list:
    if near(lat, lon, rwy_ad_coords): continue
    add(name, 'A4.4', seg, lat, lon, alt, 'BaseULM'); n_ulm += 1

# Aérodromes sans piste AIXM : cercle (A4.3) seulement si AUCUNE ULM à proximité
# (sinon la piste ULM couvre déjà le terrain) → vrais héliports/hélistations.
ulm_coords = [(u[0], u[1]) for u in ulm_list]
for cid, a in no_rwy_ads:
    if near(a['lat'], a['lon'], ulm_coords): continue
    add(f"{a['name']} ({cid})", 'A4.3', Point(a['lon'], a['lat']), a['lat'], a['lon'], a['elev'], 'AIXM')
    n_heli += 1

OUT2 = OUT.replace('.geojson', '_src.json')
json.dump(srcs, open(OUT2, 'w'), ensure_ascii=False, separators=(',', ':'))
import os
print(f"Aérodromes(pistes)={n_ad}  Hélistations={n_heli}  ULM={n_ulm}")
print(f"{len(srcs)} sources -> {OUT2}  ({os.path.getsize(OUT2)/1024:.0f} Ko)")
