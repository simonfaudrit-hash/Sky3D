#!/usr/bin/env python3
"""Pourquoi 695 espaces n'ont pas de géométrie?"""
import sys
from lxml import etree
from collections import defaultdict

path = sys.argv[1]
tree = etree.parse(path)
root = tree.getroot()

def tv(el, tag):
    f = el.find(tag)
    return f.text.strip() if f is not None and f.text else None

def parse_geo(val):
    val = val.strip(); hemi = val[-1]; digits = val[:-1]
    if '.' in digits:
        int_part, dec_part = digits.split('.')
    else:
        int_part = digits; dec_part = '00'
    if hemi in ('N','S'):
        d,m,s = int(int_part[:2]),int(int_part[2:4]),float(int_part[4:6]+'.'+dec_part) if len(int_part)>=6 else (int(int_part[:2]),int(int_part[2:4]),0.0)[2]
    else:
        d,m,s = int(int_part[:3]),int(int_part[3:5]),float(int_part[5:7]+'.'+dec_part) if len(int_part)>=7 else 0.0
    dd = d+m/60+s/3600
    return -dd if hemi in ('S','W') else dd

# Construire le dict geo comme dans le parser
BBOX = dict(lon_min=-2.5,lat_min=42.0,lon_max=3.5,lat_max=46.5)

# Types pertinents
def normalize_type(ct, lt):
    direct = {'P','R','D','CTR','TMA','CTA','ATZ','RMZ','TMZ','TRA'}
    if ct in direct: return ct
    if ct == 'D-OTHER':
        return {'VOL':'VOLTAC','PJE':'PJE','PRN':'PRN','SUR':'R','TRVL':'R'}.get(lt)
    if ct == 'RAS':
        if lt == 'RMZ': return 'RMZ'
    return None

# Lire les Ase pertinents
ase_dict = {}
for ase in root.findall('.//Ase'):
    uid = ase.find('.//AseUid')
    if uid is None: continue
    code_id = tv(uid,'codeId') or ''
    ct = (tv(uid,'codeType') or '').upper()
    lt = (tv(ase,'txtLocalType') or '').upper()
    atype = normalize_type(ct,lt)
    if not atype: continue
    val_l = tv(ase,'valDistVerLower')
    uom_l = tv(ase,'uomDistVerLower')
    lower_ft = 0
    if val_l:
        try:
            v = float(val_l)
            if (uom_l or '').upper() == 'FL': v *= 100
            lower_ft = v
        except: pass
    if lower_ft > 400: continue
    ase_dict[code_id] = {'type':atype, 'name':tv(ase,'txtName') or code_id}

print(f"Ase pertinents: {len(ase_dict)}")

# Lire les Abd
geo_dict = defaultdict(int)
for abd in root.findall('.//Abd'):
    uid = abd.find('.//AseUid')
    if uid is None: continue
    code_id = tv(uid,'codeId')
    if code_id and code_id in ase_dict:
        avxs = abd.findall('.//Avx')
        geo_dict[code_id] += len(avxs)

# Trouver les sans géométrie
no_geo = {k:v for k,v in ase_dict.items() if k not in geo_dict}
has_one = {k:v for k,v in ase_dict.items() if k in geo_dict and geo_dict[k] < 3}

print(f"Sans Abd du tout: {len(no_geo)}")
print(f"Abd avec < 3 points: {len(has_one)}")

# Types des sans géométrie
types_no_geo = defaultdict(int)
for k,v in no_geo.items():
    types_no_geo[v['type']] += 1
print(f"\nTypes sans géométrie:")
for t,n in sorted(types_no_geo.items(), key=lambda x:-x[1]):
    print(f"  {t}: {n}")

# Chercher si ces codeId apparaissent dans des Abd mais liés différemment
print(f"\nExemple de 3 Ase sans Abd:")
for i,(code_id,ase) in enumerate(list(no_geo.items())[:3]):
    print(f"  {code_id} ({ase['type']}) — {ase['name']}")
    # Chercher dans le XML si ce codeId apparaît ailleurs
    for el in root.iter():
        if el.text and el.text.strip() == code_id and el.tag == 'codeId':
            parent = el.getparent()
            gp = parent.getparent() if parent is not None else None
            ggp = gp.getparent() if gp is not None else None
            if ggp is not None and ggp.tag != 'Ase':
                print(f"    Trouvé dans: {ggp.tag}/{gp.tag}/{parent.tag}")
                print(f"    XML: {etree.tostring(ggp, pretty_print=True).decode()[:300]}")
                break

