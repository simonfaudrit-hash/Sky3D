#!/usr/bin/env python3
"""Diagnostic rapide du format XML SIA"""
import sys
from lxml import etree

path = sys.argv[1] if len(sys.argv)>1 else "AIXM4.5_all_FR_OM_2026-06-11.xml"

print(f"Lecture de {path}...")
tree = etree.parse(path)
root = tree.getroot()

print(f"\nBalise racine: {root.tag}")
print(f"Namespace: {root.nsmap}")

# Compter les enfants
children = list(root)
print(f"\nNombre d'enfants directs: {len(children)}")
print("5 premiers enfants:")
for c in children[:5]:
    print(f"  {c.tag}")

# Chercher n'importe quelle balise contenant "Airspace"
print("\nRecherche de balises contenant 'Airspace' ou 'airspace':")
count = 0
for el in root.iter():
    tag = el.tag.split('}')[-1] if '}' in el.tag else el.tag
    if 'airspace' in tag.lower() or 'Airspace' in tag:
        print(f"  {el.tag}")
        count += 1
        if count >= 10:
            print("  ...")
            break

if count == 0:
    print("  Aucune balise Airspace trouvée")
    print("\nToutes les balises distinctes:")
    tags = set()
    for el in root.iter():
        tag = el.tag.split('}')[-1] if '}' in el.tag else el.tag
        tags.add(tag)
    for t in sorted(tags)[:30]:
        print(f"  {t}")
