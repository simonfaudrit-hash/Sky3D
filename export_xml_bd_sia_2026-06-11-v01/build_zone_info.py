#!/usr/bin/env python3
"""
Infos gestionnaire / horaires / conditions / activité par zone, pour le popup.

Les zones affichées viennent du XML SIA (id = esp_pk_partie_pk), mais les
remarques + horaires d'activation sont dans l'AIXM (txtRmk, Att). On joint donc
AIXM ↔ SIA :
  - clé principale : SIA lk « [LF][D 569] » → codeId AIXM « LFD569 »
  - repli : nom normalisé (type-agnostique)

Sortie : zone_info.json  { esp_pk : {r?,h?,w?} }   (filtré aux zones de l'appli)
  r = activité / contact (txtRmk)   h = code horaire (H24/HJ/HX)
  w = horaires & conditions d'activation (txtRmkWorkHr lisible)
Injecté inline dans index.html comme `const ZONE_INFO`.
"""
import json, re, os, xml.etree.ElementTree as ET

BASE = '/Users/simonfaudrit/Desktop/Sky3D'
AIXM = f'{BASE}/export_xml_bd_sia_2026-06-11-v01/AIXM4.5_all_FR_OM_2026-06-11.xml'
SIA  = f'{BASE}/export_xml_bd_sia_2026-06-11-v01/XML_SIA_2026-06-11.xml'
OUT  = f'{BASE}/export_xml_bd_sia_2026-06-11-v01/zone_info.json'
APP_IDS = '/tmp/aip_ids.json'   # ids des zones réellement affichées (esp_pk_partie_pk)

def clean(s):
    if not s: return None
    s = s.replace('\\\\', ' / ').replace('\\', ' / ').replace('#', ' · ')
    s = re.sub(r'\s+', ' ', s).strip(' ·/')
    return s or None

def norm(s):
    return re.sub(r'[^A-Z0-9]', '', (s or '').upper())

# ── 1) AIXM : infos par codeId et par nom normalisé ──────────────────────────
by_cid, by_name = {}, {}
for ev, el in ET.iterparse(AIXM, events=('end',)):
    if el.tag != 'Ase':
        continue
    uid = el.find('AseUid')
    cid = uid.find('codeId').text if uid is not None and uid.find('codeId') is not None else None
    rmk = el.find('txtRmk'); att = el.find('Att'); nm = el.find('txtName')
    rec = {}
    r = clean(rmk.text if rmk is not None else None)
    if r: rec['r'] = r
    if att is not None:
        h = att.find('codeWorkHr'); w = att.find('txtRmkWorkHr')
        hv = (h.text or '').strip() if h is not None else ''
        wv = clean(w.text if w is not None else None)
        if hv and hv != 'H24': rec['h'] = hv          # H24 implicite/peu utile seul
        elif hv == 'H24' and not wv: rec['h'] = hv
        if wv: rec['w'] = wv
    if rec:
        if cid: by_cid[cid] = rec
        n = norm(nm.text if nm is not None else None)
        if n: by_name.setdefault(n, rec)
    el.clear()
print(f"[i] AIXM : {len(by_cid)} zones avec infos")

# ── 2) ids des zones affichées (esp_pk attendus) ─────────────────────────────
app_esp = None
if os.path.exists(APP_IDS):
    app_esp = {i.split('_')[0] for i in json.load(open(APP_IDS))}
    print(f"[i] {len(app_esp)} esp_pk présents dans l'appli")

# ── 3) SIA : esp_pk → infos via lk→codeId (repli nom) ────────────────────────
def cid_candidates(lk):
    m = re.search(r'\]\[([^\]]+)\]', lk or '')
    if not m: return []
    inner = m.group(1)
    base = 'LF' + inner.replace(' ', '')
    cands = [base]
    toks = inner.split()
    while len(toks) > 1:                     # retirer les suffixes de secteur (L, HIGH, A…)
        toks = toks[:-1]
        cands.append('LF' + ''.join(toks))
    return cands

info = {}; matched = 0; total = 0
for ev, el in ET.iterparse(SIA, events=('end',)):
    if el.tag != 'Espace':
        continue
    pk = el.get('pk'); lk = el.get('lk', '')
    if not pk or '[LF]' not in lk:
        el.clear(); continue
    if app_esp is not None and pk not in app_esp:
        el.clear(); continue
    total += 1
    rec = None
    for cid in cid_candidates(lk):
        if cid in by_cid: rec = by_cid[cid]; break
    if rec is None:
        nm = el.find('Nom')
        rec = by_name.get(norm(nm.text if nm is not None else None))
    if rec:
        info[pk] = rec; matched += 1
    el.clear()

json.dump(info, open(OUT, 'w'), ensure_ascii=False, separators=(',', ':'))
print(f"[✓] {matched}/{total} zones appli enrichies -> {OUT} ({os.path.getsize(OUT)/1024:.0f} Ko)")
for k in list(info)[:4]:
    print('  ', k, info[k])
