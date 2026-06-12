#!/usr/bin/env python3
"""Diagnostic approfondi format SIA XML"""
import sys
from lxml import etree

path = sys.argv[1]
tree = etree.parse(path)
root = tree.getroot()

# Regarder la structure d'un élément Ase
print("=== Structure d'un élément Ase (espace aérien) ===")
ases = root.findall('.//Ase')
print(f"Nombre d'Ase: {len(ases)}")

if ases:
    ase = ases[0]
    print(f"\nPremier Ase — tous les sous-éléments:")
    for child in ase.iter():
        if child.text and child.text.strip():
            tag = child.tag
            val = child.text.strip()[:60]
            print(f"  {tag}: {val}")

print("\n=== 3 exemples d'Ase ===")
for ase in ases[:3]:
    print("\n--- Ase ---")
    for child in ase:
        if child.text and child.text.strip():
            print(f"  {child.tag}: {child.text.strip()[:80]}")
        for sub in child:
            if sub.text and sub.text.strip():
                print(f"    {sub.tag}: {sub.text.strip()[:80]}")

# Regarder Abd (AirspaceBorder = géométrie)
print("\n=== Structure d'un Abd (géométrie) ===")
abds = root.findall('.//Abd')
print(f"Nombre d'Abd: {len(abds)}")
if abds:
    abd = abds[0]
    for child in abd.iter():
        if child.text and child.text.strip():
            print(f"  {child.tag}: {child.text.strip()[:80]}")
