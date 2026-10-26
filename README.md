# Meshlearning — synthetische bewegingsdata

Eerste technische demonstratie voor een commerciële full-body datagenerator:
**bekende beweging → beelden/video → referentielabels → foutanalyse**.
Gebaseerd op het werkprincipe van Lavikainen et al. (2025),
https://doi.org/10.1038/s41597-025-06243-7, zonder hun dataset, meshes,
texturen of code over te nemen.

## Ontworpen pitch beoordelen

De eerste eigen ontworpen volledige baseball pitch heeft een aparte schouderketen,
een aaneengesloten skinned mannequin, drie gesynchroniseerde aanzichten,
vertraagde weergave, fasebeelden en functionele thorax-humeruslabels.

**[Bekijk de pitch en de beoordelingshandleiding](docs/pitch/README.md).**

Dit is een tweede, afzonderlijke demonstratie naast het technische
18-segmentenmodel hieronder. De pitchrig heeft 22 segmenten/controls,
inclusief niet-anatomische vervormingshelpers. Hij is niet uitwisselbaar met
SOMA en zijn labels zijn nog geen ISB-/Movalytics-hoeken.

## Status

Dit prototype maakt een **schematische procedurele figuur met 18 segmenten**.
Het bevat pelvis, romp, nek, hoofd en bilateraal clavicula, bovenarm,
onderarm, hand, bovenbeen, onderbeen en voet. Geen vingers, afzonderlijke
scapula of afzonderlijke wervels. Dezelfde beweging wordt vanuit twee camera's
vastgelegd. Er zijn geen externe menselijke assets nodig.

De referentie is exact binnen dit technische model, **geen gevalideerde
anatomische gouden standaard**. De X/Y/Z-controls zijn uitdrukkelijk geen
ISB-hoeken. De figuur is geen realistisch trainingsavatar. Er is nog geen
SOMA-mapping, GEM-X-inferentie, modeltraining of bewezen verbetering op echte
beelden. Schaalvariatie verandert alleen de lengte, niet leeftijd of lichaamsbouw.
Zelfdoorsnijding, balans en fysiologische gewrichtskoppelingen worden nog niet
gecontroleerd. Gebruik deze beelden om de technische keten te controleren.

## Controlepakket met geïsoleerde bewegingen

```bash
.venv/bin/python -m meshlearning.cli controls --out outputs/controls-new
.venv/bin/python -m meshlearning.cli isolated-motion \
  --case thigh_L.z --frames 25 --fps 12 --out outputs/isolated-new
```

Het controlepakket schrijft expliciete definities (`definitions.json`), alle
verwachte/berekende hoeken (`angle_checks.csv`) en een leesbaar plus JSON-rapport.
Het omvat 54 **technische** assen (18 segmenten × 3) en 1.782 controles met
neutrale en gedraaide ouders en niet-neutrale rustrotaties. De fixture gebruikt
Rodrigues; de terugrekening gebruikt afzonderlijke atan2-matrixformules en
weigert gecombineerde rotaties, ongeldige matrices en de 180°-ambiguïteit.
Dit is geen vervanging voor een definitie van klinische gecombineerde hoeken.

De links/rechts-posities zijn vanaf `engineering-axes-v2` gecorrigeerd:
L ligt op negatieve X en R op positieve X, bij X = rechts van de persoon.
De eerdere preview onder `docs/preview` is een historisch v1-voorbeeld en
gebruikt nog de oude zijdeposities. Vergelijk de labels niet zonder conversie.

Het bestand van `isolated-motion` kan rechtstreeks door de renderer:

```bash
blender --background --threads 2 --python scripts/render.py -- \
  --data outputs/isolated-new/reference.npz --out outputs/isolated-new \
  --fps 12 --size 256
```

Een geel oriëntatiepunt op het actieve segment maakt axiale rotatie zichtbaar.
De beelden tonen het kanaal en de verwachte/berekende hoek. Het punt is een
technische markering, geen anatomisch landmark. De standaard amplitude ±60°
is een controletest, geen voorschrift van fysiologisch toegestane ROM.

De gegenereerde bestanden worden onder `outputs/` bewaard en niet standaard
in Git opgenomen. Een vastgelegde controle-uitvoer staat onder
[docs/controls](docs/controls/README.md), met voorbeeld-GIFs voor geïsoleerde
heuprotaties. Zie [de anatomische checklist](docs/ANGLE_DEFINITIONS.md) voor
het onderscheid tussen de huidige definities en toekomstige ISB-validatie.

## Installatie

Benodigd: Python >=3.11, Blender 4.3 met Cycles CPU, FFmpeg met libx264.
De geteste omgeving heeft Python 3.12.14, Blender 4.3.2 en NumPy 2.3.5.

```bash
cd /workspace/meshlearning
python3 -m venv .venv
.venv/bin/python -m pip install -e .
.venv/bin/python -m unittest discover -s tests -v
```

Op een eigen computer vervang je het pad door de locatie van deze repository.
Blender en FFmpeg moeten op PATH staan. Geen GPU, sleutels of betaald assetpakket
nodig voor de demonstratie. De bestaande Movalytics/GEM-X-videoroute vereist
volgens zijn documentatie CUDA en ten minste 12 GB VRAM; die is hier niet uitgevoerd.

## Een filmpje en labels maken

```bash
.venv/bin/python -m meshlearning.cli demo \
  --out outputs/my-demo --frames 48 --fps 24 --size 256 --render
```

Laat `--render` weg om alleen referentielabels te genereren. Gebruik een nieuwe,
lege uitvoermap; bestaande resultaten worden niet overschreven. CPU-rendering
gebruikt twee threads en acht samples. Dat levert een snelle controle, geen
fotorealistische dataset. `--scale 0.95` geeft uniforme lengteschaling.

Uitvoer:

- `front.mp4`, `oblique.mp4` en de bijbehorende PNG-frames;
- `reference.npz`: framenummers, tijden, segmentnamen, globale rotatiematrices,
  rustrotaties, gewrichtsposities en segmentuiteinden in meters, en controls in graden;
- `controls.csv`: dezelfde controls per segment en frame;
- `camera_labels.json`: wereld-/cameratransformaties, projectiematrices en
  2D-posities in pixels, plus `in_frame`. Dit is **geen occlusie-label**;
- `manifest.json`: coördinatenstelsel, beperkingen, herkomst en skeletstructuur.

Rechtshandige wereld: X rechts, Y voorwaarts, Z omhoog. Actieve lokale rotaties:
`Rx(x) @ Ry(y) @ Rz(z)`. Een lokale rotatie wordt door de ouderrotatie naar de
wereld getransformeerd. Alle camera's delen dezelfde referentiebeweging;
frame `00000.png` correspondeert met videoframe 0 en NPZ-frame 0.

## Rotatiematrices vergelijken

```bash
.venv/bin/python -m meshlearning.cli compare \
  --reference outputs/my-demo/reference.npz \
  --predictions predicted_rotations.npz --out outputs/rotation-error.json
```

Dit rapporteert de geodetische fout in globale segmentoriëntatie, in graden.
Namen, frames, assen en wereldreferentie moeten exact overeenkomen. Een SOMA-NPZ
van Movalytics kan daarom **niet rechtstreeks** worden vergeleken met dit eigen
skelet. Eerst is een expliciete gecontroleerde mapping nodig. Dezelfde bestandsnamen
of shapes betekenen niet dat twee skeletten anatomisch equivalent zijn.

## Movalytics-hoekuitvoer vergelijken

Voor later, zodra onafhankelijke anatomische referentiehoeken beschikbaar zijn:

```bash
.venv/bin/python -m meshlearning.cli compare-angles \
  --reference validated-reference.csv --predictions /path/to/movalytics/angles \
  --fps 60 --out outputs/clinical-comparison
```

De referentie-CSV heeft deze kolommen:

```csv
frame_idx,time_s,joint,column,value_deg
0,0,hip_L,hip_l_rot_deg,0
1,0.016666666666666666,hip_L,hip_l_rot_deg,10
```

`joint` is de Movalytics-CSV-bestandsnaam zonder `.csv`; `column` is exact de
kolomnaam in die CSV. Controleer de daadwerkelijk gebruikte kalibratie en
tekenconventie. Het voorbeeld hierboven beschrijft alleen het formaat, geen
anatomische referentiedata. Gebruik `controls.csv` hiervoor niet.

Uitvoer: `errors.csv` en `report.json`, met aantallen, MAE, RMSE, bias, maximale
fout, P95 en fouten per absolute referentiehoekbereik. Lock-flags blijven zichtbaar;
zulke frames worden niet stilzwijgend weggefilterd. Niet-eindige waarden en
onjuiste tijdstempels worden geweigerd. Geen automatische tijdverschuiving,
offsetcorrectie of tekenomkering. Alleen aangeleverde referentie-observaties
worden beoordeeld; het rapport bewijst geen dekking van alle gewrichten.

## Eerstvolgende inhoudelijke stappen

1. Versies uit de Movalytics-repository vastleggen; huidige upstream GEM-X niet
   ongemerkt als vervanger installeren.
2. Per gewricht ISB-assen, anatomische landmarks, nulstand, rotatievolgorde en
   singulariteitsbeleid vastleggen. Niet elk gewricht heeft drie onafhankelijke DOF.
3. Native SOMA-assets en hun specifieke rechten onderzoeken. Koppeling aan
   onafhankelijke anatomische referentie controleren met geïsoleerde én gecombineerde
   rotaties; klinische referenties niet uit dezelfde Movalytics-kalibratie afleiden.
4. Realistische buitenkant, lichaamsvormvariatie en contact-/botsingscontrole.
5. Filmpjes in het door `tools/run_gemx/run_gemx.py` verwachte formaat analyseren;
   fouten vóór en na Movalytics afzonderlijk meten.
6. GPU-bijtraining en onafhankelijke echte validatie. Splits op lichaamsidentiteit
   en bewegingsfamilie vóór cameravariatie, zodat dezelfde beweging niet via een
   andere camera in training en test terechtkomt. Rapporteer eindstanden apart.

## Rechten en herkomst

De demonstratie gebruikt eigen procedurele geometrie en bewegingen; geen
SMPL/SKEL/BEDLAM-, MakeHuman- of SOMA-assets zijn meegeleverd. Blender, NumPy
en FFmpeg behouden hun eigen licenties. Er is geen projectbrede open-sourcelicentie
gekozen namens HU/Babon; spreek eigendom en distributierechten af vóór publicatie.
Dit prototype is geen bevestiging van commerciële rechten op toekomstige assets.
Zie [PROVENANCE.md](PROVENANCE.md).
