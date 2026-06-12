#!/usr/bin/env python3
"""Analyser pourquoi les VOLTAC n'ont pas de géométrie"""
import sys
from lxml import etree

path = sys.argv[1]
tree = etree.parse(path)
root = tree.getroot()

# 1. Trouver quelques Ase VOL avec leur codeId
print("=== 5 premiers Ase VOL (VOLTAC) ===")
voltac_ids = []
for ase in root.findall('.//Ase'):
    uid = ase.find('.//AseUid')
    lt  = ase.find('txtLocalType')
    if uid is None or lt is None: continue
    if lt.text and lt.text.strip().upper() == 'VOL':
        ct_el = uid.find('codeType')
        ci_el = uid.find('codeId')
        nm_el = ase.find('txtName')
        mid   = uid.get('mid','')
        code_id = ci_el.text if ci_el is not None else '?'
        voltac_ids.append((code_id, mid))
        if len(voltac_ids) <= 5:
            print(f"  codeId={code_id} mid={mid} name={nm_el.text if nm_el is not None else '?'}")

print(f"\nTotal VOL: {len(voltac_ids)}")

# 2. Chercher leurs Abd par codeId ET par mid
if voltac_ids:
    cid, mid = voltac_ids[0]
    print(f"\n=== Recherche Abd pour codeId={cid}, mid={mid} ===")

    # Par codeId
    found_by_id = 0
    found_by_mid = 0
    for abd in root.findall('.//Abd'):
        ase_uid = abd.find('.//AseUid')
        if ase_uid is None: continue
        ci = ase_uid.find('codeId')
        m  = ase_uid.get('mid','')
        if ci is not None and ci.text == cid:
            found_by_id += 1
            print(f"  Trouvé par codeId! mid={m}")
            print(etree.tostring(abd, pretty_print=True).decode()[:400])
        if m == mid:
            found_by_mid += 1
    print(f"  Par codeId: {found_by_id}, par mid: {found_by_mid}")

# 3. Chercher par AseUidBase ou AseUidComponent (zones composites)
print("\n=== Vérifier AseUidBase/Component dans Abd ===")
for abd in root.findall('.//Abd')[:5]:
    base = abd.find('.//AseUidBase')
    comp = abd.find('.//AseUidComponent')
    if base is not None or comp is not None:
        print(etree.tostring(abd, pretty_print=True).decode()[:300])
        break

# 4. Vérifier les Abd orphelins (avec codeId inconnu)
print("\n=== Exemple d'Abd dont le codeId n'est dans aucun Ase VOL ===")
# Chercher un Abd qui contient 'VOL' dans son codeId ou son AseUid
for abd in root.findall('.//Abd'):
    ase_uid = abd.find('.//AseUid')
    if ase_uid is None: continue
    ci = ase_uid.find('codeId')
    ct = ase_uid.find('codeType')
    if ci is not None and ct is not None:
        if 'VOL' in (ci.text or '').upper() or ct.text == 'D-OTHER':
            avxs = abd.findall('.//Avx')
            if len(avxs) > 2:
                print(f"  codeId={ci.text} codeType={ct.text} avx={len(avxs)}")
                print(etree.tostring(abd, pretty_print=True).decode()[:500])
                break
