#!/usr/bin/env python3
"""Diagnostic liaison Ase/Abd + structure Avx"""
import sys
from lxml import etree

path = sys.argv[1]
tree = etree.parse(path)
root = tree.getroot()

# Afficher le XML brut des 2 premiers Abd
print("=== XML brut des 3 premiers Abd ===")
for i, abd in enumerate(root.findall('.//Abd')[:3]):
    print(f"\n--- Abd {i+1} ---")
    print(etree.tostring(abd, pretty_print=True).decode()[:1000])

# Afficher le XML brut d'un Ase qui a des altitudes
print("\n=== XML brut d'un Ase avec altitudes ===")
for ase in root.findall('.//Ase'):
    txt = etree.tostring(ase, pretty_print=True).decode()
    if 'valDistVer' in txt:
        print(txt[:800])
        break

# Chercher comment Ase et Abd sont liés
print("\n=== Structure AseUid dans Abd ===")
for abd in root.findall('.//Abd')[:3]:
    uid = abd.find('.//AseUid')
    if uid is not None:
        print("AseUid trouvé:", etree.tostring(uid).decode())
    else:
        # Chercher tout élément contenant 'Uid' ou 'id'
        for el in abd:
            print(f"  Enfant direct de Abd: {el.tag}")
            for sub in el:
                print(f"    {sub.tag}: {sub.text}")
