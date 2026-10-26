# Herkomst en commerciële controle

| Onderdeel | Huidig gebruik | Rechtenstatus |
|---|---|---|
| Skelet/geometrie/bewegingen | Procedureel in deze repository gemaakt | Geen externe mens-assets; projecteigendom/distributielicentie nog afspreken |
| NumPy | Matrixberekeningen | BSD; geïnstalleerde distributie behoudt eigen notices |
| Blender | Externe CPU-renderer | GPL-software; render-output valt niet automatisch onder GPL |
| FFmpeg/libx264 | Externe video-encoder | Build-afhankelijke LGPL/GPL-voorwaarden; niet als binary meegeleverd |
| Nature-artikel/Godosim | Methode onderzocht en geciteerd | Artikel CC BY 4.0; genoemde scripts/modules MIT; voorbeeld-dataset niet-commercieel; geen code/assets gekopieerd |
| Movalytics | CSV-interface onderzocht | Babon-licentie; samenwerking HU/Babon gemeld; concrete commerciële/distributierechten niet uit samenwerking afgeleid |
| GEM-X/SOMA | Geplande integratie, niet uitgevoerd | Code, modelgewichten en concrete assets afzonderlijk controleren en versies vastzetten |

Onderzochte Movalytics-commit: `887de80c8966c1afcd35c5c685b8c59625bf6682`.
Bronnen:
- https://github.com/Babon-Innovations-b-v/movalytics
- https://github.com/jerela/Godosim#license-and-copyright
- https://doi.org/10.1038/s41597-025-06243-7
- Kardolus et al., arXiv:2607.17639v1, door gebruiker aangeleverde PDF.

Voor elke later toegevoegde asset: bron-URL, exacte versie/hash, licentietekst,
recht op commerciële training, verkoop van gegenereerde data, redistributie van
het bronasset en attribution-verplichtingen vastleggen. Deze rechten zijn
verschillende vragen; toestemming voor één impliceert de andere niet.

## Ontworpen pitch v1

De beweging in `configs/pitch_v1.json` is opgebouwd uit eigen numerieke keyframes;
er is geen externe mocap, sportvideo of gedownloade animatie gebruikt. De
licentie op een bestaande bewegingsdataset is daardoor geen afhankelijkheid.
De door `scripts/render_pitch.py` gemaakte mesh, rig, materiaalinstellingen,
markeringen en balmarker zijn origineel procedureel. Er worden geen externe
mensmodellen, huidtexturen, foto's, add-ons of auteursrechtelijke meshbestanden
ingeladen. Dat is geen anatomische of juridische certificering van het project.

De reviewtools gebruiken Pillow en Matplotlib, met hun eigen licenties;
er worden geen distributiebinaries of fontbestanden meegeleverd.
Brondata en ontwerpkeuzes staan expliciet in de review. Het is geen gemeten
beweging van een echte persoon en geen digitale kopie van een specifieke pitcher.

## Pitch v2 en framecontract

V2 gebruikt dezelfde originele procedurele geometrie met eigen regionale huidgewichten
en aangepaste eigen keyframes. De vergelijking van huidbinding gebruikt identieke
V1-bronposes. Virtuele anatomische landmarks zijn modelaannames, geen metingen.
De Movalytics-audit leest de openbare interface en bewaart commit/hash/structuur;
er is geen Babon-code of kalibratietabel gekopieerd of meegeleverd. De werkelijke
registraties naar SOMA zijn expliciet onbekend; er zijn geen extra lichaamsassets
of modelgewichten gedownload voor deze aansluiting.

## Exacte SOMA-/Movalytics-controle

De officiële SOMA-template op commit 86632764684281dc98f31ab9c4aac36a4cdbc428
is alleen buiten de checkout gedownload, met verificatie van de LFS-SHA256.
De menselijke geometrie wordt niet in onze rendering gebruikt en het USD-bestand
wordt niet gepubliceerd. De afgeleide frameconventie, bronhashes en aannames
zijn expliciet vastgelegd. De ongewijzigde Movalytics-software en kalibratie zijn
vanuit een afzonderlijke, vastgelegde checkout op CPU uitgevoerd; geen
Babon-code of kalibratiebestand wordt meegeleverd. Numerieke onderzoeksresultaten
verwijzen naar Kardolus et al., arXiv:2607.17639v1, en de oorspronkelijke repository.
Deze controle verleent geen aanvullende rechten op derdencomponenten en bewijst
geen klinische juistheid. De oorspronkelijke werkende kalibratie-invoer is een
open verificatiepunt, niet stilzwijgend gerepareerd of opnieuw gefit.

## Volwassen lichaamsvormen

De slanke en vollere variant zijn eigen parametrische vervormingen van onze
oorspronkelijke procedurele mesh. Geen externe lichaamsmodellen, demografische
scans, texturen of nieuwe afhankelijkheden zijn toegevoegd. Het zijn geen
gevalideerde leeftijds- of BMI-modellen; het skelet en de pitch blijven gelijk.

## Geometrische schouderreferentie

De landmarkframes, expliciete YXY-conventie en controles zijn in dit project
geïmplementeerd. Er wordt geen kalibratie geleerd of aangepast. De zelfstandige
referentie heeft alleen NumPy nodig; de onafhankelijke verificatie gebruikt SciPy
(BSD). Wu et al. (2005) wordt geciteerd; Spartacus is alleen als publieke
conventie-kruiscontrole gelezen, zonder code of datasets over te nemen.
Alle gepubliceerde controlelandmarks, rotaties en pitchlabels zijn gegenereerde
modeldata. Dit is geen validatie van gemeten anatomie of SOMA-registratie.

## Voetbaltrap v1

De voetbalbeweging bestaat uit eigen numerieke sleutelstanden en interpolatie,
met expliciete rechterheup-/knie-/enkelcontrols en een linker standvoet via IK. De
bestaande eigen mesh, rig en oppervlaktevarianten worden hergebruikt. De bal
is procedureel gemaakt, zonder textuur of extern model. Er is geen externe
mocap, sportvideo, Kimodo-beweging of kledingasset gebruikt. De balbeweging
is een illustratie, geen dynamische simulatie. Heup-/knie-/enkellabels blijven
modelcontrols en zijn niet als ISB-gevalideerde anatomische hoeken aangeduid.
