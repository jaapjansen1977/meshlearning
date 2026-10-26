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
