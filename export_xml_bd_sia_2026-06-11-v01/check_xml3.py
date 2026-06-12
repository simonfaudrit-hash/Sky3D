#!/usr/bin/env python3
"""Diagnostic complet format SIA — structure Ase + Abd + limites verticales"""
import sys
from lxml import etree

path = sys.argv[1]
tree = etree.parse(path)
root = tree.getroot()

# Structure complète d'un Ase avec géométrie
print("=== Ase complet avec AseUid ===")
for ase in root.findall('.//Ase')[:2]:
    print("\n--- Ase complet ---")
    for el in ase.iter():
        if el.text and el.text.strip():
            print(f"  {el.tag}: {el.text.strip()}")

# Structure Abd (géométrie)
print("\n=== Abd complet (3 premiers) ===")
for abd in root.findall('.//Abd')[:3]:
    print("\n--- Abd ---")
    for el in abd.iter():
        if el.text and el.text.strip():
            print(f"  {el.tag}: {el.text.strip()}")

# Chercher les limites verticales
print("\n=== Chercher valUpper/valLower dans Ase ===")
for ase in root.findall('.//Ase'):
    txt = etree.tostring(ase, encoding='unicode')
    if 'valUpper' in txt or 'valLower' in txt or 'Upper' in txt:
        print("\nAse avec limites verticales:")
        for el in ase.iter():
            if el.text and el.text.strip():
                print(f"  {el.tag}: {el.text.strip()}")
        break

# Lier Ase et Abd via AseUid
print("\n=== Liaison Ase → Abd via AseUid ===")
# Chercher un AseUid dans Abd
for abd in root.findall('.//Abd')[:2]:
    print("\n--- Abd avec AseUid ---")
    for el in abd.iter():
        if el.text and el.text.strip():
            print(f"  {el.tag}: {el.text.strip()}")
