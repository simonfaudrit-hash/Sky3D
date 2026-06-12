# Sky3D — Contexte projet pour Claude Code

## Ce qu'est Sky3D
Application web de visualisation des espaces aériens français en volumes 3D interactifs.
Public cible : pilotes de drones, pour comprendre les restrictions (notamment la limite de 120m AGL).
Source de données officielle : DGAC / SIA (format AIXM 4.5 et XML SIA).

---

## Stack technique

- **Rendu carte** : MapLibre GL 4.7.1
- **Rendu 3D** : Deck.gl 9.0 (PolygonLayer extrudé, TextLayer)
- **Données** : GeoJSON embarqué inline dans index.html (`const AIP`)
- **Pipeline données** : Python (sia_parser_v5.py) → GeoJSON → intégration manuelle dans le HTML
- **Architecture** : Single-file SPA (HTML + CSS + JS dans index.html)
- **Pas de framework JS** (vanilla JS)
- **Pas de bundler** (pas de npm, pas de build step)

---

## Structure des fichiers

```
Sky3D/
├── index.html                              ← App principale (version de travail actuelle)
├── dronesky_v7.html                        ← Version précédente (référence UI)
└── export_xml_bd_sia_2026-06-11-v01/
    ├── AIXM4.5_all_FR_OM_2026-06-11.xml   ← Source DGAC officielle
    ├── XML_SIA_2026-06-11.xml
    ├── sia_parser_v5.py                    ← Parser principal (utiliser cette version)
    ├── airspaces_sudouest_drones.geojson   ← Données intermédiaires
    └── check_*.py                          ← Scripts de validation
```

---

## Structure de index.html

| Lignes | Contenu |
|--------|---------|
| 1–109 | CSS + HTML (panel latéral, popup, slider altitude) |
| 110–116 | Imports MapLibre GL + Deck.gl |
| 119 | `const AIP` — GeoJSON embarqué (~400 Ko) |
| 122–140 | `const T` — Types de zones et couleurs RGB |
| 142–150 | `const S` — État global (filtres, altMax, show3D, showLabels) |
| 152–179 | `makeStyle()` + `mlMap` — Fond de carte (OSM/Satellite/Hybride/Dark) |
| 181–206 | Instance Deck.gl synchronisée avec MapLibre |
| 208–323 | `render()` — Rendu 3D/2D des couches |
| 324–416 | Fonctions UI (stats, sliders, filtres, popup) |
| 418–429 | Init au chargement |

---

## Logique de rendu

La fonction `render()` génère 3 couches Deck.gl :
- **`bg-3d`** : PolygonLayer semi-transparent → zones CTR, TMA, CTA, SIV, RTBA, ATZ, RMZ
- **`fg-3d`** : PolygonLayer opaque → zones P, R, D, VOLTAC, PJE, ZSM (restrictives)
- **`labels`** : TextLayer optionnel centré sur chaque polygone

En mode 2D : un seul `GeoJsonLayer` remplace les deux PolygonLayer.

MapLibre et Deck.gl sont synchronisés via `onViewStateChange` → `mlMap.jumpTo()`.

---

## État global `const S`

```js
S.on          // Set des types de zones actifs (filtres)
S.altMax      // Altitude max affichée (en mètres)
S.show3D      // Mode 3D ou 2D
S.showLabels  // Labels visibles ou non
```

---

## Conventions à respecter

- **Ne pas fragmenter le fichier** : index.html reste un single-file. Ne pas proposer de séparation en modules sauf si explicitement demandé.
- **Ne pas introduire de bundler** (webpack, vite, etc.) sans validation.
- **Préserver la structure commentée** par sections dans index.html.
- **Les données (`const AIP`) ne doivent pas être modifiées** sauf si le pipeline Python a été relancé.
- Pour le pipeline Python, toujours utiliser `sia_parser_v5.py` (pas les versions précédentes).
- Versionner : les anciennes versions (v7) sont conservées comme référence, ne pas les écraser.

---

## Objectifs en cours

- [ ] Visualisation correcte de la restriction drone 120m AGL
- [ ] UI enrichie (référence : dronesky_v7.html pour les éléments visuels réussis)
- [ ] Futur : export vers mobile (PWA ou React Native)

---

## Ce que je suis

Développeur débutant. Privilégier des explications claires. Proposer une seule solution à la fois, pas plusieurs options simultanées. Valider avant de faire des changements structurels importants.
