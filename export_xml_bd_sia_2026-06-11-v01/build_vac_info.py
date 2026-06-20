#!/usr/bin/env python3
"""
Contact gestionnaire des aérodromes/ULM/terrains privés depuis les FICHES VAC
(PDF dans les dossiers départementaux 1-ain/, 65-pyrenees-atlantiques/, …).
Chaque fiche (ex. LFIX.pdf, LF0121.pdf) a un bloc structuré :
  Gestionnaire : … / Contact : … / Tél : … / mail : … / Observations : …

Sortie : vac_info.json  { CODE : {n,g?,t?,m?,o?} }
  CODE = nom de fichier (LFIX, LF6457…) = OACI pour les AD, code BaseULM sinon
  n = nom normalisé (jointure ULM par toponyme)  g = gestionnaire  t = tél
  m = mail  o = observations (tronquées)
Injecté inline dans index.html comme `const VAC_INFO`.
"""
import re, json, os, glob
from pypdf import PdfReader

BASE = '/Users/simonfaudrit/Desktop/Sky3D'
OUT  = f'{BASE}/export_xml_bd_sia_2026-06-11-v01/vac_info.json'

def norm(s):
    return re.sub(r'[^a-z0-9]', '', (s or '').lower())

def grab(text, label, maxlen=None):
    m = re.search(label + r'\s*:\s*([^\n]+)', text)
    if not m: return None
    v = re.sub(r'\s+', ' ', m.group(1)).strip(' -')
    if maxlen and len(v) > maxlen: v = v[:maxlen].rstrip() + '…'
    return v or None

def grab_multi(text, label, maxlen):
    """Capture un bloc multi-ligne (ex. Observations) jusqu'au pied de fiche."""
    m = re.search(label + r'\s*:\s*(.+?)(?:\n\s*Fiche\b|\Z)', text, re.S)
    if not m: return None
    v = re.sub(r'\s+', ' ', m.group(1)).strip(' -·')
    if len(v) > maxlen: v = v[:maxlen].rsplit(' ', 1)[0] + '…'
    return v or None

pdfs = sorted(glob.glob(f'{BASE}/[0-9]*/*.pdf'))
info = {}
errors = 0
for path in pdfs:
    code = os.path.splitext(os.path.basename(path))[0]
    try:
        text = PdfReader(path).pages[0].extract_text() or ''
    except Exception:
        errors += 1; continue
    first = (text.split('\n', 1)[0] or '').strip()
    name = re.sub(r'\s*' + re.escape(code) + r'\s*$', '', first).strip()
    rec = {'n': norm(name)}
    g = grab(text, 'Gestionnaire')           # « Gestionnaire : X » (pas « Gestionnaire terrain: »)
    t = grab(text, r'T[ée]l')
    m = grab(text, 'mail')
    o = grab_multi(text, 'Observations', 240)
    if g: rec['g'] = g
    if t and re.search(r'\d', t): rec['t'] = t
    if m and '@' in m: rec['m'] = m
    if o: rec['o'] = o
    if rec.get('g') or rec.get('t') or rec.get('m'):
        info[code] = rec

json.dump(info, open(OUT, 'w'), ensure_ascii=False, separators=(',', ':'))
print(f"{len(pdfs)} fiches lues ({errors} erreurs) — {len(info)} avec contact "
      f"-> {OUT} ({os.path.getsize(OUT)/1024:.0f} Ko)")
for k in ('LFIX', 'LF6457', 'LF0121'):
    if k in info: print(' ', k, info[k])
