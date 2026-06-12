#!/usr/bin/env python3
"""VOLTAC avec plancher SFC + structure Abd complète"""
import sys
from lxml import etree

path = sys.argv[1]
tree = etree.parse(path)
root = tree.getroot()

def tv(el, tag):
    f = el.find(tag)
    return f.text.strip() if f is not None and f.text else None

# Trouver les VOLTAC plancher SFC
print("=== VOLTAC avec plancher SFC (0 ft) ===")
sfc_ids = []
for ase in root.findall('.//Ase'):
    uid = ase.find('.//AseUid')
    lt  = ase.find('txtLocalType')
    if uid is None or lt is None: continue
    if (lt.text or '').strip().upper() != 'VOL': continue
    
    val_l = tv(ase, 'valDistVerLower') or '0'
    try:
        lower = float(val_l)
    except:
        lower = 0
    
    if lower == 0:
        code_id = tv(uid, 'codeId') or ''
        name    = tv(ase, 'txtName') or ''
        val_u   = tv(ase, 'valDistVerUpper') or '?'
        uom_u   = tv(ase, 'uomDistVerUpper') or ''
        sfc_ids.append(code_id)
        if len(sfc_ids) <= 10:
            print(f"  {code_id} — {name} — plancher SFC — plafond {val_u} {uom_u}")

print(f"\nTotal VOLTAC plancher SFC: {len(sfc_ids)}")

# Voir l'Abd du premier
if sfc_ids:
    cid = sfc_ids[0]
    print(f"\n=== Abd complet pour {cid} ===")
    for abd in root.findall('.//Abd'):
        uid = abd.find('.//AseUid')
        if uid is None: continue
        ci = uid.find('codeId')
        if ci is not None and ci.text == cid:
            print(etree.tostring(abd, pretty_print=True).decode())
            break
