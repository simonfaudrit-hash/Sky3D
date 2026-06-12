#!/usr/bin/env python3
"""Voir la structure complète d'un Avx CWA/CCA"""
import sys
from lxml import etree

path = sys.argv[1]
tree = etree.parse(path)
root = tree.getroot()

print("=== XML complet d'un Abd avec CWA ou CCA ===")
found = 0
for abd in root.findall('.//Abd'):
    has_arc = any(
        avx.find('codeType') is not None and
        avx.find('codeType').text in ('CWA','CCA')
        for avx in abd.findall('.//Avx')
    )
    if has_arc:
        print(etree.tostring(abd, pretty_print=True).decode()[:2000])
        found += 1
        if found >= 2:
            break
