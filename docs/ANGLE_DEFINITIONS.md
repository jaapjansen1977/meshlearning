# Hoekdefinities en anatomische status

## Vastgelegd in engineering-axes-v2

- Rechtshandig assenstelsel, actieve rotaties op kolomvectoren.
- Neutraal: rechte benen en armen omlaag, voeten naar anterior.
- X = rechts van de persoon; Y = anterior; Z = superior.
- Links ligt op negatieve X; rechts op positieve X.
- Elke proef beweegt precies één segment ten opzichte van de ouder, rond één as.
- `R_local = R_parent_world.T @ R_child_world`.
- `R_local = R_motion @ R_rest_local`; dus `R_motion = R_local @ R_rest_local.T`.
- Positief volgt de rechterhandregel rond de expliciete getekende as in
  `definitions.json`. Alle andere lokale bewegingen blijven nul.
- Terugrekening geeft de getekende hoofdhoek in (-180°, 180°). 180° is uitgesloten
  omdat het teken niet uniek is. Meerdere omlopen worden niet ondersteund.
- 90° wordt bij deze **enkelassige** proeven ondersteund; dit is geen algemene
  Euler-decompositie en voorkomt niet de singulariteiten van gecombineerde hoeken.
- In de eerdere gemengde demo blijft `Rx(x) @ Ry(y) @ Rz(z)` gelden. Die Euler-
  controls zijn niet hetzelfde als een klinische joint coordinate system.

De volledige machineleesbare definitie bevat per kanaal de ouder, het kind,
de getekende as, voorlopige klinische interpretatie, nulstand en teststanden.
Het rapport legt de SHA256 van die definitie vast. Zo is duidelijk welke
conventie bij een resultaat hoorde.

## Voorlopige geometrische interpretaties

| Gewricht | Positieve richting in de neutrale figuur | Status |
|---|---|---|
| Heup | Flexie: +X; abductie: links +Y/rechts -Y; endorotatie: links -Z/rechts +Z | Geometrisch getest, anatomische framevalidatie ontbreekt |
| Schouderproxy | Zelfde tekenafspraken als heup | Clavicula-bovenarm zonder scapula; geen volwaardig schoudercomplex |
| Knie | Flexie: -X; onderbeen beweegt posterior | Alleen flexie heeft hier een voorlopige klinische interpretatie |
| Elleboogproxy | Flexie: +X; onderarm beweegt anterior | Geen gescheiden radius/ulna of gevalideerde pronatie-as |
| Enkel-/voetproxy | Dorsiflexie: +X; voorvoet beweegt superior | Geen gescheiden talocruraal/subtalair model |
| Pelvis, romp, nek, hoofd, clavicula, pols en overige assen | Rechterhandregel rond expliciete technische X/Y/Z-as | Nog geen klinische interpretatie toegekend |

54 technische assen zijn **geen verklaring dat de mens 54 onafhankelijke
bewegingsvrijheden op deze gewrichten heeft**. Testwaarden zoals ±120° zijn
algebraïsche stresstests en kunnen anatomisch onmogelijke standen opleveren.
De assen vallen in de procedurele neutraalstand samen met de wereldassen;
zij zijn niet uit individuele botlandmarks bepaald.

## Nodig vóór het label 'ISB-gevalideerd'

Per gewricht moeten de relevante aanbeveling, anatomische landmarks,
segmentframes, nulstand, bewegingstekens, joint-coordinate-system/rotatievolgorde
en singulariteitsbeleid worden vastgelegd en getoetst. Schouder vraagt expliciete
keuzes over thorax, clavicula, scapula en humerus. Onderarm en voet kunnen niet
zonder onderbouwing als één generiek drieassig scharnier behandeld worden.

Relevante aanbevelingen om de uitwerking aan te toetsen:

- Wu et al. (2002), ISB recommendation on definitions of joint coordinate systems,
  part I: ankle, hip and spine. DOI: 10.1016/S0021-9290(01)00222-6.
- Wu et al. (2005), part II: shoulder, elbow, wrist and hand.
  DOI: 10.1016/j.jbiomech.2004.05.042.

Deze verwijzingen betekenen niet dat de huidige modelassen die aanbevelingen
al implementeren. Ook een exact numeriek roundtrip-resultaat bewijst dat niet.

## Aansluiting op Movalytics

De huidige uitvoer kan niet als SOMA-NPZ aan de standaard Movalytics-kalibratie
worden gevoerd. Namen, segmentframes en ruststanden verschillen. Een correctie
van namen alleen is onvoldoende. De gebruikte Movalytics-versie en kalibratie
moeten expliciet gekoppeld worden aan een gecontroleerde skeleton-/framemapping.

De volgende integratiecontrole vergelijkt onafhankelijke anatomische labels met
Movalytics-uitvoer uit exacte segmentrotaties, gevolgd door dezelfde vergelijking
met door GEM-X geschatte rotaties. Dat houdt fouten in hoekextractie en in
beeldschatting gescheiden. Deze twee integratiecontroles zijn nog niet uitgevoerd.
