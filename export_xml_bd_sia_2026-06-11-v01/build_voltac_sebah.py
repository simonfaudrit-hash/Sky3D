#!/usr/bin/env python3
"""
Reconstruit la géométrie officielle des secteurs VOLTAC / SETBA / SEBAH
à partir de :
  - FR-ENR-5.3-fr-FR.pdf      (tables de coordonnées officielles SIA)
  - AIXM4.5_all_FR_OM_*.xml   (tracés de frontières Gbr → suivi de frontière)
Sortie : voltac_sebah.geojson  (planchers SFC, à injecter dans index.html)
"""
import re, json, xml.etree.ElementTree as ET
from pypdf import PdfReader
from shapely.geometry import Polygon, MultiPolygon, box, mapping

# Subdivision en maille (~3 km) : chaque cellule se drape finement sur le terrain
# (deck.gl triangule les polygones pleins depuis le contour seul → peu de sommets = drapage grossier)
GRID_STEP = 0.04  # degrés (~3-4 km) — compromis détail de drapage / taille fichier
def gridify(geom):
    minx, miny, maxx, maxy = geom.bounds
    cells = []
    x = minx - (minx % GRID_STEP)
    while x < maxx:
        y = miny - (miny % GRID_STEP)
        while y < maxy:
            inter = box(x, y, x + GRID_STEP, y + GRID_STEP).intersection(geom)
            if not inter.is_empty:
                if inter.geom_type == 'Polygon':
                    cells.append(inter)
                elif inter.geom_type == 'MultiPolygon':
                    cells.extend(g for g in inter.geoms if g.geom_type == 'Polygon')
            y += GRID_STEP
        x += GRID_STEP
    return MultiPolygon(cells) if cells else geom

BASE = '/Users/simonfaudrit/Desktop/Sky3D'
PDF  = f'{BASE}/FR-ENR-5.3-fr-FR.pdf'
AIXM = f'{BASE}/export_xml_bd_sia_2026-06-11-v01/AIXM4.5_all_FR_OM_2026-06-11.xml'
OUT  = f'{BASE}/export_xml_bd_sia_2026-06-11-v01/voltac_sebah.geojson'

# ─── Frontières Gbr (AIXM) ───────────────────────────────────────────────────
def _gbv(lat, lon):
    def p(s):
        s = s.strip(); h = s[-1]; s = s[:-1]
        if h in 'NS': dd, mm, ss = float(s[0:2]), float(s[2:4]), float(s[4:])
        else:         dd, mm, ss = float(s[0:3]), float(s[3:5]), float(s[5:])
        v = dd + mm/60 + ss/3600
        return -v if h in 'SW' else v
    return [round(p(lon), 6), round(p(lat), 6)]

GBRS = {}
for ev, el in ET.iterparse(AIXM, events=('end',)):
    if el.tag == 'Gbr':
        GBRS[el.find('GbrUid/txtName').text] = [
            _gbv(g.find('geoLat').text, g.find('geoLong').text) for g in el.findall('Gbv')]
        el.clear()

def merge_borders(names):
    segs = [list(GBRS[n]) for n in names if n in GBRS and GBRS[n]]
    if not segs: return []
    chain = segs.pop(0)
    d = lambda a, b: (a[0]-b[0])**2 + (a[1]-b[1])**2
    while segs:
        best = bi = chosen = None
        for i, s in enumerate(segs):
            for sp in (s, s[::-1]):
                dd = d(chain[-1], sp[0])
                if best is None or dd < best: best, bi, chosen = dd, i, sp
        chain += chosen[1:]; segs.pop(bi)
    return chain

def splice(ptA, ptB, border):
    if not border: return []
    nidx = lambda p: min(range(len(border)), key=lambda i: (border[i][0]-p[0])**2 + (border[i][1]-p[1])**2)
    iA, iB = nidx(ptA), nidx(ptB)
    return border[iA:iB+1] if iA <= iB else border[iB:iA+1][::-1]

# ─── Parse coordonnées (deux formats PDF) ────────────────────────────────────
RE_SPACE = re.compile(r"(\d{2})\s+(\d{2})\s+(\d{2})\s*([NS])\s*[-/]?\s*(\d{2,3})\s+(\d{2})\s+(\d{2})\s*([EW])")
RE_SYM   = re.compile(r"(\d{1,2})°\s?(\d{2})\D{1,2}?\s?(\d{2})\D{0,3}?\s?([NS])\s*[-/]?\s*(\d{1,3})°\s?(\d{2})\D{1,2}?\s?(\d{2})\D{0,3}?\s?([EW])")
def to_dec(d, m, s, h):
    v = float(d) + float(m)/60 + float(s)/3600
    return -v if h in 'SW' else v
def parse_coord(line):
    for rx in (RE_SPACE, RE_SYM):
        m = rx.search(line)
        if m:
            return [round(to_dec(*m.group(5,6,7,8)), 6), round(to_dec(*m.group(1,2,3,4)), 6)]
    return None

def border_for(text):
    t = text.lower()
    if 'allemagne' in t or 'german' in t:            return ['FRANCE_GERMANY']
    if 'belg' in t:                                   return ['BELGIUM_FRANCE']
    if 'luxembourg' in t:                             return ['FRANCE_LUXEMBOURG']
    if 'itali' in t:                                  return ['FRANCE_ITALY']
    if 'écrins' in t or 'ecrins' in t:                return ['FRANCE:PARC DES ECRINS']
    if 'andorr' in t:                                 return ['FRANCE_SPAIN_EAST', 'ANDORRA_SPAIN']
    if 'espagn' in t or 'spanish' in t or 'spain' in t: return ['FRANCE_SPAIN_WEST', 'FRANCE_SPAIN_EAST', 'ANDORRA_SPAIN']
    return None
def is_border_line(line):
    t = line.lower()
    return (('frontièr' in t or 'frontier' in t or 'border' in t or 'écrins' in t or 'ecrins' in t)
            and not parse_coord(line))

reader = PdfReader(PDF)
plines = lambda i: [l.strip() for l in (reader.pages[i].extract_text() or '').split('\n') if l.strip()]

# ─── Assemblage d'un ring (points + segments frontière) ──────────────────────
def build_ring(els):
    ring = []
    for i, (kind, val) in enumerate(els):
        if kind == 'pt':
            if not ring or ring[-1] != val: ring.append(val)
        else:  # frontière entre point précédent et point suivant (ou fermeture)
            prev = ring[-1] if ring else None
            nxt = next((els[j][1] for j in range(i+1, len(els)) if els[j][0] == 'pt'), None)
            if nxt is None and ring: nxt = ring[0]
            if prev and nxt:
                for p in splice(prev, nxt, merge_borders(val)):
                    if not ring or ring[-1] != p: ring.append(p)
    if ring and ring[0] != ring[-1]: ring.append(ring[0])
    return ring

# ─── VOLTAC (pages 9-11 : identifiant APRÈS les coords) ──────────────────────
ID_RE = re.compile(r'^VOLTAC\s+([A-Z]{2,3})(?:\s+(N|S|NE|PM))?\s*$')
def parse_voltac():
    out = {}
    for pg in (9, 10, 11):
        lines = plines(pg); buf = []
        for idx, ln in enumerate(lines):
            c = parse_coord(ln)
            if c: buf.append(('pt', c)); continue
            if is_border_line(ln):
                bf = border_for(ln)
                if bf: buf.append(('bd', bf))
                continue
            m = ID_RE.match(ln)
            if m:
                name = m.group(1) + ((' ' + m.group(2)) if m.group(2) else '')
                if not m.group(2) and idx+1 < len(lines) and lines[idx+1] in ('PM', 'NE', 'N', 'S'):
                    name += ' ' + lines[idx+1]
                out['VOLTAC ' + name] = (buf, 0, 500, 'SFC', '500 ft ASFC'); buf = []
    return out

# ─── SETBA (pages 3-7 : identifiant AVANT les coords) ────────────────────────
def parse_setba():
    out = {}; cur = None; buf = []
    for pg in range(3, 8):
        for ln in plines(pg):
            m = re.match(r'^Secteur\s+([A-ZÉÈÀÂÔ][\wÉÈÀÂÔçé\' ()\-]{1,30})$', ln)
            if m and not parse_coord(ln):
                if cur and buf: out[cur] = (buf, 0, 500, 'SFC', '500 ft ASFC')
                cur = 'SETBA ' + m.group(1).strip().rstrip('.'); buf = []
                continue
            c = parse_coord(ln)
            if c and cur: buf.append(('pt', c)); continue
            if is_border_line(ln) and cur:
                bf = border_for(ln)
                if bf: buf.append(('bd', bf))
    if cur and buf: out[cur] = (buf, 0, 500, 'SFC', '500 ft ASFC')
    return out

# ─── SEBAH (pages 13,15 : points numérotés "N/ coords") ──────────────────────
def parse_sebah(pg, name, upper_ft, upper_str):
    els = []
    for ln in plines(pg):
        c = parse_coord(ln)
        if c: els.append(('pt', c)); continue
        if is_border_line(ln):
            bf = border_for(ln)
            if bf: els.append(('bd', bf))
    return {name: (els, 0, upper_ft, 'SFC', upper_str)}

# ─── Construction GeoJSON ────────────────────────────────────────────────────
zones = {}
zones.update(parse_voltac())
zones.update(parse_setba())
zones.update(parse_sebah(13, 'SEBAH SAINTE-LÉOCADIE', 10000, '10000 ft AMSL'))
zones.update(parse_sebah(15, 'SEBAH BRIANÇON', 12000, '12000 ft AMSL'))

feats = []
for name, (els, lo, up, ls, us) in zones.items():
    ring = build_ring(els)
    if len(ring) < 4:
        print(f"  ⚠ {name}: ring trop court ({len(ring)}), ignoré"); continue
    poly = Polygon(ring).buffer(0)
    if poly.is_empty:
        print(f"  ⚠ {name}: polygone vide, ignoré"); continue
    poly = poly.simplify(0.0008, preserve_topology=True)  # ~75 m, réduit les frontières lourdes
    label = name.split()[0]  # VOLTAC / SETBA / SEBAH
    if label in ('VOLTAC', 'SEBAH'):
        poly = gridify(poly)   # maille fine → drapage terrain (les SETBA manuels ne sont pas injectés)
    feats.append({'type': 'Feature', 'geometry': json.loads(json.dumps(mapping(poly))),
        'properties': {'id': 'enr53_' + re.sub(r'\W+', '_', name), 'name': name,
            'type': 'VOLTAC', 'type_label': label, 'class': '',
            'lower_ft': lo, 'upper_ft': up, 'lower_str': ls, 'upper_str': us,
            'lower_m': 0, 'upper_m': round(up*0.3048, 1), 'height_m': round(up*0.3048, 1),
            'color': '#FF6600', 'opacity': 0.45, 'source': 'ENR-5.3 + AIXM frontières'}})
    g = poly.geoms[0] if poly.geom_type == 'MultiPolygon' else poly
    print(f"  {name:26s} {label:6s} {g.exterior.coords.__len__():3d}pts aire={poly.area:.4f} valide={poly.is_valid}")

json.dump({'type': 'FeatureCollection', 'features': feats}, open(OUT, 'w'), ensure_ascii=False)
print(f"\n{len(feats)} zones écrites -> {OUT}")
PYEOF_MARKER = None
