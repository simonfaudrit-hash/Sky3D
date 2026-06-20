#!/usr/bin/env python3
"""
Contact gestionnaire des aérodromes/hélistations depuis le XML SIA <Ad>.
Clé = code OACI (= AdAfs[:4], ex. LFBO), qui correspond au codeId AIXM utilisé
dans les noms de la couche AD_REST (« TOULOUSE BLAGNAC (LFBO) »).

Sortie : aero_info.json  { OACI : {g?,t?,a?,h?} }
  g = gestionnaire (AdGestion)   t = téléphone (AdTel)
  a = adresse (AdAdresse)        h = horaires BRIA/info (HorBiaTxt)
Injecté inline dans index.html comme `const AERO_INFO`.
"""
import json, re, os, xml.etree.ElementTree as ET

BASE = '/Users/simonfaudrit/Desktop/Sky3D'
SIA  = f'{BASE}/export_xml_bd_sia_2026-06-11-v01/XML_SIA_2026-06-11.xml'
OUT  = f'{BASE}/export_xml_bd_sia_2026-06-11-v01/aero_info.json'

def clean(s):
    if not s: return None
    s = s.replace('\\\\', ' / ').replace('\\', ' / ').replace('#', ' · ')
    s = re.sub(r'\s+', ' ', s).strip(' ·/')
    return s or None

info = {}
for ev, el in ET.iterparse(SIA, events=('end',)):
    if el.tag != 'Ad':
        continue
    afs = (el.findtext('AdAfs') or '').strip()
    icao = afs[:4] if len(afs) >= 4 else None
    if not icao:
        el.clear(); continue
    rec = {}
    g = clean(el.findtext('AdGestion')); t = clean(el.findtext('AdTel'))
    a = clean(el.findtext('AdAdresse')); h = clean(el.findtext('HorBiaTxt'))
    if g: rec['g'] = g
    if t: rec['t'] = t
    if a: rec['a'] = a
    if h: rec['h'] = h
    if rec.get('g') or rec.get('t'):       # ne garder que les vrais contacts
        info[icao] = rec
    el.clear()

json.dump(info, open(OUT, 'w'), ensure_ascii=False, separators=(',', ':'))
print(f"{len(info)} aérodromes avec contact -> {OUT} ({os.path.getsize(OUT)/1024:.0f} Ko)")
for k in list(info)[:4]:
    print('  ', k, info[k])
