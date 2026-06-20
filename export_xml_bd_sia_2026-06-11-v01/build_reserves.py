#!/usr/bin/env python3
"""
Contours précis + gestionnaire des réserves naturelles (zones PRN de l'AIP, qui
ne sont que des cercles de protection). Source : WFS Géoplateforme IGN, couche
patrinat_rnn:rnn (RNN = réserves naturelles nationales) → nom_site, gest_site,
url_fiche, géométrie.

Téléchargement des sources (WFS Géoplateforme, EPSG:4326) — non commitées :
  base="https://data.geopf.fr/wfs/ows?SERVICE=WFS&VERSION=2.0.0&REQUEST=GetFeature&outputFormat=application/json&srsName=EPSG:4326&count=1000"
  curl "$base&typeNames=patrinat_rnn:rnn"          -o rnn_raw.geojson   # réserves nat. nationales
  curl "$base&typeNames=patrinat_rnc:pnm"          -o rnc_raw.geojson   # réserves nat. de Corse
  curl "$base&typeNames=patrinat_pn:parc_national" -o pn_raw.geojson    # parcs nationaux (cœur+adhésion)

Entrée  : rnn_raw / rnc_raw / pn_raw.geojson, + noms PRN lus dans index.html
Sortie  :
  - prn_real_add.json  { "PRN <NOM>" : <MultiPolygon simplifié> }  (à fusionner
    dans PRN_REAL, contours manquants seulement)
  - reserve_info.json  { "PRN <NOM>" : {g, f} }  g=gestionnaire f=fiche INPN
"""
import re, json, unicodedata
from shapely.geometry import shape, mapping

BASE = '/Users/simonfaudrit/Desktop/Sky3D'
HTML = f'{BASE}/index.html'
RNN  = f'{BASE}/export_xml_bd_sia_2026-06-11-v01/rnn_raw.geojson'

STOP = {'de','du','des','la','le','les','et','d','l','aux','a','au','sur','en','the',
        'parc','national','reserve','naturelle','nationale','ile','iles','plateau','massif'}
def stem(w):
    return w[:-1] if len(w) > 4 and w.endswith('s') else w
def toks(s):
    s = unicodedata.normalize('NFKD', s or '').encode('ascii','ignore').decode().lower()
    s = re.sub(r'[^a-z0-9]', ' ', s)
    return {stem(w) for w in s.split() if w and w not in STOP}

def jacc(a, b):
    return len(a & b) / len(a | b) if (a or b) else 0

# ── PRN de l'app + PRN_REAL existant ────────────────────────────────────────
html = open(HTML).read()
aip = json.loads(re.search(r'const AIP\s*=\s*(\{.*?\});', html, re.S).group(1))
prn_names = sorted({f['properties']['name'] for f in aip['features']
                    if f['properties'].get('type') == 'PRN'})
existing = set()
m = re.search(r'const PRN_REAL = (\{.*?\});', html, re.S)
if m: existing = set(json.loads(m.group(1)).keys())

# ── Index par tokens : RNN + RNC + Parcs Nationaux (cœur) ───────────────────
DIR = f'{BASE}/export_xml_bd_sia_2026-06-11-v01'
src = []
src += json.load(open(RNN))['features']
src += json.load(open(f'{DIR}/rnc_raw.geojson'))['features']
src += [f for f in json.load(open(f'{DIR}/pn_raw.geojson'))['features']
        if 'Adh' not in (f['properties'].get('zone') or '')]   # Cœur de parc (pas l'aire d'adhésion)
ref_idx = [(toks(f['properties'].get('nom_site')), f) for f in src]

def best_match(name):
    t = toks(re.sub(r'^PRN\s+', '', name))
    best, bf = 0, None
    for rt, f in ref_idx:
        sc = jacc(t, rt)
        if rt and rt <= t: sc = max(sc, 0.8)        # réf ⊆ nom AIP (ex. Marais d'Yves ⊆ Baie et marais d'Yves)
        if t and t <= rt: sc = max(sc, 0.7)         # nom AIP ⊆ réf (ex. Cerbicale ⊆ Iles Cerbicale)
        if sc > best and (t & rt) and max(len(w) for w in (t & rt)) >= 4:
            best, bf = sc, f
    return (bf, best) if best >= 0.5 else (None, best)

geoms, info, miss = {}, {}, []
for name in prn_names:
    f, sc = best_match(name)
    if not f:
        miss.append(name); continue
    p = f['properties']
    info[name] = {}
    if p.get('gest_site'): info[name]['g'] = p['gest_site']
    if p.get('url_fiche'): info[name]['f'] = p['url_fiche']
    if name not in existing:                          # contour manquant → on l'ajoute
        g0 = shape(f['geometry'])
        tol = 0.0012 if g0.area > 0.02 else 0.0003     # gros parcs → simplification +
        g = g0.simplify(tol, preserve_topology=True)
        gj = mapping(g)
        def rnd(c):                                     # arrondir à 4 décimales (~11 m)
            return [round(c[0], 4), round(c[1], 4)] if isinstance(c[0], (int, float)) else [rnd(x) for x in c]
        gj = {'type': gj['type'], 'coordinates': rnd(gj['coordinates'])}
        g2 = shape(gj)
        if not g2.is_valid: g2 = g2.buffer(0)           # corrige les auto-intersections APRÈS arrondi
        geoms[name] = mapping(g2)

json.dump(geoms, open(f'{BASE}/export_xml_bd_sia_2026-06-11-v01/prn_real_add.json','w'),
          ensure_ascii=False, separators=(',',':'))
json.dump(info, open(f'{BASE}/export_xml_bd_sia_2026-06-11-v01/reserve_info.json','w'),
          ensure_ascii=False, separators=(',',':'))
print(f"PRN app: {len(prn_names)} | déjà contour: {len(existing & set(prn_names))}")
print(f"matchés RNN: {len(info)} | nouveaux contours ajoutés: {len(geoms)}")
print(f"sans match RNN ({len(miss)}):")
for n in miss: print('   ', n)
print('Yves:', 'PRN BAIE ET MARAIS D\'YVES' in info, info.get("PRN BAIE ET MARAIS D'YVES"))
