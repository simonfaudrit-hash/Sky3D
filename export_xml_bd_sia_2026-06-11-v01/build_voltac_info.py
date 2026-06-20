#!/usr/bin/env python3
"""
Extrait le contact gestionnaire par secteur VOLTAC / SETBA / SEBAH depuis le PDF
ENR 5.3 (colonne « Point de contact »). Un bloc contact précède les zones qu'il
couvre (ex. « Base école Général Navelet, DAX » → VOLTAC DAX N + DAX S).

Sortie : voltac_info.json  { id_zone : {g?,t?,m?,u?} }
  id_zone = 'enr53_' + nom assaini (même clé que voltac_sebah.geojson)
  g = organisme/adresse   t = téléphone   m = courriel   u = utilisateur habituel
Injecté inline dans index.html comme `const VOLTAC_INFO`.
"""
import re, json, os
from pypdf import PdfReader

BASE = '/Users/simonfaudrit/Desktop/Sky3D'
PDF  = f'{BASE}/FR-ENR-5.3-fr-FR.pdf'
OUT  = f'{BASE}/export_xml_bd_sia_2026-06-11-v01/voltac_info.json'

reader = PdfReader(PDF)
plines = lambda i: [l.strip() for l in (reader.pages[i].extract_text() or '').split('\n') if l.strip()]

COORD = re.compile(r'\d{2}\s?\d{2}\s?\d{2}.*[NS].*\d{2,3}\s?\d{2}\s?\d{2}.*[EW]')
VOLTAC_ID = re.compile(r'^VOLTAC\s+([A-Z]{2,3})(?:\s+(N|S|NE|PM))?\s*$')
SETBA_ID  = re.compile(r"^Secteur\s+([A-ZÉÈÀÂÔ][\wÉÈÀÂÔçé' ()\-]{1,30})$")

def zone_id(name):
    return 'enr53_' + re.sub(r'\W+', '_', name)

def parse_contact(block):
    """block : liste de lignes depuis 'Point de contact' jusqu'aux limites/coords."""
    text = '\n'.join(block)
    rec = {}
    me = re.search(r'[\w.\-]+@[\w.\-]+\.\w+', text)
    if me: rec['m'] = me.group(0)
    mt = re.search(r'TEL\s*:?\s*([0-9][0-9 /]{6,})', text)
    if mt: rec['t'] = re.sub(r'\s+', ' ', mt.group(1)).strip(' /')
    # organisme : lignes après l'entête 'Point de contact' jusqu'à 'Utilisation'
    org, started = [], False
    for l in block:
        ll = l.lower()
        if 'point de contact' in ll: started = True; continue
        if not started: continue
        if any(k in ll for k in ('point of contact', 'utilisation', 'conditions of use',
               'utilisateur', 'regular user', 'coordination', 'tel ', 'tel:', 'fax',
               'courriel', 'e-mail')): break
        org.append(l)
    if org: rec['g'] = ', '.join(org[:3])
    # utilisateur habituel (ligne suivant le libellé, version FR)
    for i, l in enumerate(block):
        if 'utilisateur habituel' in l.lower() and i+1 < len(block):
            rec['u'] = block[i+1]; break
    return rec

def harvest(pages, id_re, name_fn):
    out = {}
    cur = None
    cap, capturing = [], False
    for pg in pages:
        lines = plines(pg)
        for idx, ln in enumerate(lines):
            if 'point de contact' in ln.lower():
                capturing, cap = True, [ln]; continue
            if capturing:
                if COORD.search(ln) or 'ft /' in ln.lower() or ln.upper() == 'SFC':
                    cur = parse_contact(cap); capturing = False
                else:
                    cap.append(ln); continue
            m = id_re.match(ln)
            if m and cur:
                out[zone_id(name_fn(lines, idx, m))] = cur
    return out

def voltac_name(lines, idx, m):
    name = m.group(1) + ((' ' + m.group(2)) if m.group(2) else '')
    if not m.group(2) and idx+1 < len(lines) and lines[idx+1] in ('PM', 'NE', 'N', 'S'):
        name += ' ' + lines[idx+1]
    return 'VOLTAC ' + name

def setba_name(lines, idx, m):
    return 'SETBA ' + m.group(1).strip().rstrip('.')

info = {}
info.update(harvest((9, 10, 11), VOLTAC_ID, voltac_name))
info.update(harvest((3, 4, 5, 6, 7), SETBA_ID, setba_name))
# Ne garder que les contacts exploitables (organisme identifié) : les SETBA aux
# pages à colonnes bancales ne donnent qu'un TEL hors contexte → écartés (ils
# retombent sur le bloc générique « PC OPS dédié, voir ENR 5.3 »).
info = {k: v for k, v in info.items() if v.get('g')}

json.dump(info, open(OUT, 'w'), ensure_ascii=False, separators=(',', ':'))
print(f"{len(info)} secteurs avec contact -> {OUT} ({os.path.getsize(OUT)/1024:.0f} Ko)")
for k, v in info.items():
    print(' ', k, '->', v.get('g', '?')[:40], '| TEL', v.get('t'), '| @', v.get('m'))
