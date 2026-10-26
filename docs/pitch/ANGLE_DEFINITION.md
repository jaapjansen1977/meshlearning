# Wat betekenen de pitchlabels?

Dit is een eigen functionele conventie voor de ontworpen beweging. Het zijn
**geen gevalideerde ISB-hoeken en geen Movalytics-uitvoer**. De volledige
thorax-humerusrotatiematrix blijft in het lokale `motion.npz` beschikbaar,
zodat later een gecontroleerde anatomische conversie mogelijk is.

## Frames en formule

Rechtshandige wereld: X rechts van de persoon, Y voorwaarts in de beoogde
werprichting, Z omhoog. Alle matrices zijn actieve rotaties op kolomvectoren.

```text
R_HT = R_thorax_world.T @ R_humerus_world
R_HT = Rz(plane) @ Ry(-elevation) @ Rz(axial)   [rechterarm]
```

De lokale humeruslengte-as is -Z. Bij elevatie 0 hangt de bovenarm omlaag.
Bij elevatie 90 en vlak 0 wijst de rechterbovenarm lateraal naar rechts.
Een positief vlak brengt de geheven arm vanuit lateraal naar anterior;
een negatief vlak brengt hem naar posterior. Axiaal positief is in deze
ontworpen rechterarm intern gericht; negatief is extern gericht.

De linkerarm gebruikt de gespiegelde conventie met
`S = diag(-1, 1, 1)` en `R_mirrored = S @ R_HT @ S` vóór dezelfde terugrekening.
Dit levert opnieuw een echte rotatie (determinant +1), geen spiegelmesh.

## Onafhankelijke terugrekening

De bovenarmrichting wordt berekend als `d = R_HT @ [0,0,-1]`.

- Elevatie: `atan2(sqrt(d_x²+d_y²), -d_z)`.
- Vlak: `atan2(d_y, d_x)`.
- Axiaal: verwijder vlak en elevatie uit R_HT en bepaal de resterende Z-rotatie.

Bij elevatie 0 of 180 zijn vlak en axiaal niet afzonderlijk identificeerbaar.
Die hoeken worden als ongeldig/NaN gemarkeerd. De pitch vermijdt deze standen.
Deze definitie is bedoeld voor herkenbare, controleerbare ontwerpvariabelen;
het is geen oplossing voor alle klinische singulariteiten.

De waarde **-135 graden op het ontworpen maximale-exorotatiemoment is een
ontwerpkeuze in deze conventie**. Vergelijk dit getal niet rechtstreeks met
gepubliceerde pitchmetingen of met de Babon-applicatie. Daarvoor moeten
frames, nulstand en hoekdefinitie eerst worden gekoppeld.

De elleboogkolom is een ingestelde flexie-control, geen afzonderlijk uit
anatomische landmarks terugberekende ISB-ellebooghoek.

## Onderliggende schouderrig

Thorax → clavicula → scapulacontrol → deltoid-helper → humerus → onderarm → hand.
De deltoid-helper is geen extra anatomisch bot. Hij verdeelt een deel van de
twist over de vervorming van de schouder. Het mesh wordt met een armature en
volumebehoudende skinning vervormd.

De clavicula-/scapulacontroles zijn heuristische functies van de ontworpen
armheffing en het bewegingsvlak. Zij zijn niet gemeten en hun segmentframes
zijn niet uit anatomische scapulalandmarks bepaald. Ze ondersteunen de
uiterlijke beweging; ze worden niet als voorspelde klinische uitkomsten
gepresenteerd. De humerusoriëntatie ten opzichte van de thorax wordt apart
vastgelegd en de lokale humerusrotatie ten opzichte van zijn ouder wordt
daaruit afgeleid. Daardoor wordt scapulabeweging niet onbedoeld nogmaals
bij de gewenste thorax-humerusrotatie opgeteld.

## Snelheid

De bron bevat 505 standen op 240 Hz, van 0 tot en met 2,1 s. Voor de video
wordt iedere vierde stand gerenderd: 127 beelden op oorspronkelijke 60 Hz.
Afspeelsnelheid 15 fps maakt de review viermaal vertraagd. Alle tabellen en
grafieken gebruiken de oorspronkelijke ontwerptijd. De bronbeweging is een
C1-gladde interpolatie van eigen keyframes, geen opgenomen pitcher.
