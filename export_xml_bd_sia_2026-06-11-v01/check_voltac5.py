#!/usr/bin/env python3
"""Tous les VOLTAC avec leurs altitudes + structure Abd"""
import sys
from lxml import etree

path = sys.argv[1]
tree = etree.parse(path)
root = tree.getroot()

def tv(el, tag):
    f = el.find(tag)
    return f.text.strip() if f is not None and f.text else None

# Tous les VOLTAC avec altitudes
print("=== Tous les VOLTAC et leurs altitudes ===")
voltac_ids = []
for ase in root.findall('.//Ase'):
    uid = ase.find('.//AseUid')
    lt  = ase.find('txtLocalType')
    if uid is None or lt is None: continue
    if (lt.text or '').strip().upper() != 'VOL': continue
    
    code_id = tv(uid, 'codeId') or ''
    name    = tv(ase, 'txtName') or ''
    val_l   = tv(ase, 'valDistVerLower') or '?'
    uom_l   = tv(ase, 'uomDistVerLower') or ''
    cod_l   = tv(ase, 'codeDistVerLower') or ''
    val_u   = tv(ase, 'valDistVerUpper') or '?'
    uom_u   = tv(ase, 'uomDistVerUpper') or ''
    
    if any(x in name.upper() for x in ['DAX','PAU','VOLTAC']):
        print(f"  {code_id:10s} {name:30s} lower={val_l} {uom_l} ({cod_l}) upper={val_u} {uom_u}")
        voltac_ids.append(code_id)

print(f"\n=== Abd du premier VOLTAC DAX/PAU ===")
if voltac_ids:
    cid = voltac_ids[0]
    for abd in root.findall('.//Abd'):
        uid = abd.find('.//AseUid')
        if uid is None: continue
        ci = uid.find('codeId')
        if ci is not None and ci.text == cid:
            print(etree.tostring(abd, pretty_print=True).decode())
            break
