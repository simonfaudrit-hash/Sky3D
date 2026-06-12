#!/usr/bin/env python3
"""Extraire la vraie structure de la CTR LFBD depuis le XML SIA"""
import sys
from lxml import etree

path = sys.argv[1]
tree = etree.parse(path)
root = tree.getroot()

def tv(el, tag):
    f = el.find(tag)
    return f.text.strip() if f is not None and f.text else None

# Chercher les CTR de Bordeaux, Toulouse, Pau
targets = ['LFBD', 'LFBO', 'LFBP', 'LFBZ', 'LFMT']

for abd in root.findall('.//Abd'):
    uid = abd.find('.//AseUid')
    if uid is None: continue
    ct = uid.find('codeType')
    ci = uid.find('codeId')
    if ct is None or ct.text != 'CTR': continue
    if ci is None or ci.text not in targets: continue
    
    print(f"\n=== CTR {ci.text} ===")
    print(etree.tostring(abd, pretty_print=True).decode())
