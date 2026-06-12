#!/usr/bin/env python3
"""Chercher les VOLTAC et analyser le bug des arcs"""
import sys
from lxml import etree

path = sys.argv[1]
tree = etree.parse(path)
root = tree.getroot()

# 1. Chercher VOLTAC dans les noms
print("=== Recherche VOLTAC ===")
count = 0
voltac_types = set()
for ase in root.findall('.//Ase'):
    name_el = ase.find('txtName')
    uid = ase.find('.//AseUid')
    if name_el is None or uid is None:
        continue
    name = name_el.text or ''
    if 'VOLTAC' in name.upper() or 'VOL' in name.upper():
        code_type = uid.find('codeType')
        code_id   = uid.find('codeId')
        local     = ase.find('txtLocalType')
        t = code_type.text if code_type is not None else '?'
        i = code_id.text if code_id is not None else '?'
        l = local.text if local is not None else ''
        voltac_types.add(t)
        if count < 10:
            print(f"  codeType={t} localType={l} codeId={i} name={name}")
        count += 1

print(f"\nTotal VOLTAC trouvés: {count}")
print(f"Types utilisés: {voltac_types}")

# 2. Tous les codeType distincts dans le fichier
print("\n=== Tous les codeType/localType dans Ase ===")
types = {}
for ase in root.findall('.//Ase'):
    uid = ase.find('.//AseUid')
    if uid is None: continue
    ct = uid.find('codeType')
    lt = ase.find('txtLocalType')
    key = (ct.text if ct is not None else '?',
           lt.text if lt is not None else '')
    types[key] = types.get(key, 0) + 1

for (ct, lt), n in sorted(types.items(), key=lambda x: -x[1])[:25]:
    print(f"  codeType={ct:15s} localType={lt:10s} : {n}")

# 3. Analyser le bug des arcs (Avx avec codeType ABE/ABN/CWA/CCA)
print("\n=== Types d'Avx dans les Abd ===")
avx_types = {}
for abd in root.findall('.//Abd'):
    for avx in abd.findall('.//Avx'):
        ct = avx.find('codeType')
        t = ct.text if ct is not None else '?'
        avx_types[t] = avx_types.get(t, 0) + 1

for t, n in sorted(avx_types.items(), key=lambda x: -x[1]):
    print(f"  {t}: {n}")

# 4. Exemple d'un Avx d'arc
print("\n=== XML brut d'un Abd avec arc ===")
for abd in root.findall('.//Abd'):
    for avx in abd.findall('.//Avx'):
        ct = avx.find('codeType')
        if ct is not None and ct.text in ('ABE','ABN','CWA','CCA','ARC'):
            print(etree.tostring(abd, pretty_print=True).decode()[:600])
            break
    else:
        continue
    break
