#!/usr/bin/env python3
"""Structure complète d'un Ase VOLTAC"""
import sys
from lxml import etree

path = sys.argv[1]
tree = etree.parse(path)
root = tree.getroot()

print("=== XML complet des 3 premiers Ase VOL ===")
count = 0
for ase in root.findall('.//Ase'):
    uid = ase.find('.//AseUid')
    lt  = ase.find('txtLocalType')
    if uid is None or lt is None: continue
    if lt.text and lt.text.strip().upper() == 'VOL':
        print(etree.tostring(ase, pretty_print=True).decode())
        count += 1
        if count >= 3: break
