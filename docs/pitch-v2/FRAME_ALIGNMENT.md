# Van modelassen naar ISB-georiënteerde frames en Movalytics

Er zijn nu expliciete frameconstructies en een gecontroleerd interfacecontract.
Dat is een stap verder dan alleen een naam aan een ontwerpcontrol geven.
**De anatomische plaatsing is nog niet gemeten en de daadwerkelijke
model-naar-SOMA-registratie is nog niet vastgesteld.**

## 1. Welke assen zie je in de video?

De pijlen draaien met de thorax mee. Ze staan op de borst en worden boven
op het beeld geprojecteerd; het zijn geen zichtbare botten of fysiek gemeten markers.

| Kleur | Modelas in de review | Overeenkomstige ISB-georiënteerde modelas |
|---|---|---|
| Rood | X: rechts van de persoon | Z: rechts |
| Groen | Y: anterior / voorwaarts | X: anterior |
| Blauw | Z: superior / omhoog | Y: superior |

De pijlen volgen de werkelijke thoraxrotatie in de brondata, niet de
camerarichting. Zo zijn rotatie, achteroverbewegen en vooroverbuigen beter te beoordelen.

## 2. Segmentframes uit virtuele landmarks

De thoraxconstructie gebruikt IJ, C7, PX en T8. De bovenarmconstructie gebruikt
GH en de laterale/mediale epicondyl (EL/EM). Dit zijn **ontworpen virtuele punten**
op ons model; zij zijn niet afkomstig uit palpatie, beeldvorming of een
anatomisch gevalideerde mesh.

- Thorax Y: van het midden van PX/T8 naar het midden van IJ/C7.
- Thorax Z: normaal op het vlak IJ, C7 en het onderste middenpunt; naar rechts.
- Thorax X: gemeenschappelijke loodlijn, naar anterior; het frame wordt georthogonaliseerd.
- Humerus Y: van het midden van EL/EM naar GH, dus proximaal.
- Humerus X: loodrecht op de lengte-as en epicondylaire richting, naar anterior in de ontworpen nulstand.
- Humerus Z: de resterende rechterhandige as; de links/rechts-keuze is expliciet vastgelegd.

Voor deze virtuele geometrie geeft dit de vaste basisconversie:

```text
C = [[0,0,1],
     [1,0,0],
     [0,1,0]]
R_landmark_world = R_model_world @ C
R_landmark_HT = C.T @ R_model_HT @ C
```

Het gaat hier om oriëntatieframes. IJ en GH zijn de bedoelde anatomische
oorsprongen; de getekende pijlen zijn voor leesbaarheid op de borst geplaatst.
De rotatievergelijking is onafhankelijk van deze grafische plaatsing.

De code bouwt de frames opnieuw uit de virtuele punten op, in plaats van
alleen kolomnamen om te wisselen. Tests controleren dat beide berekeningen
voor dezelfde punten overeenkomen, ook bij romprotatie en voor beide armen.
Dat bewijst interne consistentie, geen juistheid van de aangenomen landmarks.

## 3. Y-X-Y-hoekrepresentatie

Als ISB-georiënteerde schouderrepresentatie gebruiken we een intrinsieke
Y-X-Y-volgorde. Voor de ontworpen rechterarm:

```text
R_landmark_HT = Ry(alpha) @ Rx(beta) @ Ry(gamma)
alpha = bewegingsvlak-control
beta  = -elevatie-control
gamma = axiale-control
```

Voor links zijn de tekens respectievelijk -,+,- ten opzichte van dezelfde
functionele controls. In `angles.csv` staan de ruwe waarden apart als
`R_landmark_proxy_yxy_alpha_deg`, `beta_deg`, `gamma_deg` en analoog voor links.
Die heten bewust **landmark_proxy**, niet gevalideerde klinische hoeken.
Bij elevatie 0 of 180 zijn vlak en axiaal niet afzonderlijk bepaalbaar;
de uitkomst wordt dan ongeldig/NaN gemarkeerd.

De relevante ISB-aanbeveling is Wu et al. (2005), deel II,
DOI 10.1016/j.jbiomech.2004.05.042. De virtuele puntplaatsing, zijdeconventies,
asinterpretatie en extreme gecombineerde standen moeten nog klinisch worden
getoetst voordat we 'ISB-gevalideerd' kunnen zeggen.

## 4. Wat verwacht de bestaande Movalytics-kalibratie?

De onderzochte versie is vastgelegd in [frame-contract.json](frame-contract.json),
inclusief commit en hashes van de interface en kalibratie. De bron is:
[Babon Movalytics, commit 887de80](https://github.com/Babon-Innovations-b-v/movalytics/tree/887de80c8966c1afcd35c5c685b8c59625bf6682).

| Uitkomst | Oudersement | Kindsegment |
|---|---|---|
| shoulder_R | Chest | RightArm |
| shoulder_L | Chest | LeftArm |

Movalytics gebruikt voor `soma_gemx_v14` swing-twist-decompositie met gekalibreerde
assen, tekens, gewichten en offsets. Dat is **niet rechtstreeks dezelfde
Y-X-Y-decompositie** als hierboven. Een naamsverandering of aspermuta­tie
is dus geen voldoende aansluiting.

Een belangrijk detail uit `tools/run_gemx/run_gemx.py`: de export geeft
identiteitsmatrices als rustrotaties mee. Volgens de runnerdocumentatie is de
bind-oriëntatie verwerkt in de gefitte kalibratieassen. Onze eigen A-pose-
rustmatrices invullen zou de ingang van deze kalibratie veranderen.

## 5. De benodigde registratie is nu precies gedefinieerd

Voor elk segment moet B de SOMA-segmentassen in ons modelsegmentframe beschrijven.
Een gemeenschappelijke wereldconversie G is afzonderlijk toegestaan:

```text
R_SOMA_segment = G @ R_model_segment @ B_segment
R_SOMA_local   = B_Chest.T @ R_model_HT @ B_Arm
```

De wereldconversie G valt weg uit de lokale rotatie. Tests met verschillende,
bekende registraties controleren deze eigenschap en de inverse omzetting.
De implementatie **weigert** een omzetting als de registratiematrices ontbreken;
er is geen automatische aanname dat B gelijk is aan de identiteitsmatrix.

`B_Chest`, `B_RightArm` en `B_LeftArm` staan daarom nog op `null` in het contract.
De model/ISB-conversie C is niet zomaar een geldige vervanger voor deze B's.
Om B vast te stellen zijn overeenkomende statische/anatomische referentieframes
van de vastgelegde SOMA-versie nodig, gevolgd door controles op meerdere
niet-collineaire en gecombineerde bewegingen.

## Wel en niet uitgevoerd

**Wel:** expliciete virtuele landmarkframes, Y-X-Y-terugrekening, geometrische
links/rechts-controles, matrixregistratie-tests en een leescontrole op de
werkelijke Movalytics-interface en kalibratiestructuur.

**Nog niet:** anatomische validatie van de landmarks, registratie naar de echte
SOMA-frames, uitvoeren van de Movalytics-kalibratie op deze pitch of GEM-X-inferentie.
We publiceren daarom geen Movalytics-foutcijfers of claims over klinische nauwkeurigheid.
