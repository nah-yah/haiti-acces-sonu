# Accès aux soins obstétricaux d'urgence sous blocage routier, Haïti

## Contexte

Santé Commune Initiative (SCI) est une ONG fictive spécialisée en santé reproductive. Dans un premier travail, elle avait identifié les communes haïtiennes où concentrer un programme de santé sexuelle et reproductive, à partir de la demande potentielle et de la densité des infrastructures. Deux ans plus tard, elle veut compléter ce ciblage par l'accessibilité effective des structures.

Désigner les bonnes communes ne suffit pas. Une femme confrontée à une urgence obstétricale doit encore pouvoir rejoindre une structure capable de la prendre en charge, ce qui suppose des routes praticables et des hôpitaux ouverts.

Le commanditaire et son mandat sont fictifs. Les données sont réelles et publiques.

## Question

Quelle part de la demande obstétricale haïtienne se situe à moins d'une heure d'un hôpital, et comment cette accessibilité varie-t-elle lorsque des tronçons routiers sont coupés ou que des structures ferment ?

## Données

| Source              | Jeu                                              | Niveau                                     | Licence          |
| ------------------- | ------------------------------------------------ | ------------------------------------------ | ---------------- |
| HOT / OpenStreetMap | Réseau routier                                   | 133 449 tronçons, dont 97 650 carrossables | ODbL             |
| WorldPop            | Population maillée 2020, contrainte, ajustée ONU | 100 m, agrégée à 1 km                      | CC BY 4.0        |
| OCHA COD-AB         | Limites administratives                          | 140 communes                               | CC BY-IGO        |
| OCHA COD-PS         | Population 2024 par sexe et âge                  | Commune                                    | CC BY-IGO        |
| HOT / OpenStreetMap | Structures de santé                              | 2 073 points                               | ODbL             |
| ACLED via HDX       | Violences contre les civils                      | Commune, mensuel                           | Conditions ACLED |

Sources, URL et limites détaillées dans `data/README_data.md`.

## Méthode

### Construction du réseau

Chaque paire de points consécutifs d'une polyligne OSM devient une arête. Les coordonnées sont arrondies au mètre avant le dédoublonnage des sommets, ce qui redonne au réseau sa topologie : deux tronçons qui se croisent au même endroit partagent alors le même nœud. Le graphe compte 1,33 million de sommets, 1,36 million d'arêtes et 36 755 km de routes.

Les vitesses représentent des temps de parcours effectifs, volontairement inférieurs aux vitesses réglementaires. Dans l'aire métropolitaine de Port-au-Prince, elles sont réduites de 45 % pour la congestion. Les valeurs et leur justification sont dans `src/config.py`.

### Estimation de la demande

Les données WorldPop sont agrégées en cellules d'environ 1 km, puis redressées commune par commune sur les populations 2024 du COD-PS. WorldPop fournit la distribution spatiale, le COD-PS fixe les totaux communaux.

Chaque cellule est pondérée par la part communale des femmes de 15 à 49 ans. Au total, 8 259 cellules portent 11,9 millions d'habitants et 3,25 millions de femmes en âge de procréer.

### Calcul de l'accessibilité

Un Dijkstra multi-sources part de toutes les structures retenues à la fois. Le graphe étant non orienté, un seul parcours donne, pour chaque nœud, le temps vers la structure la plus proche.

Le trajet entre le centre d'une cellule et le nœud routier le plus proche est compté à 4 km/h avec un facteur de détour de 1,3, ce qui intègre le déplacement hors réseau.

### Identification des tronçons critiques

La criticité s'évalue en deux temps. Une présélection retient les tronçons selon la demande qui les emprunte sur les itinéraires les plus rapides. Une seconde passe mesure directement la perte d'accessibilité que leur suppression provoque.

Cette mesure directe porte sur 150 tronçons présélectionnés, espacés d'au moins 3 km. Pour chacun, l'accessibilité de tout le pays est recalculée sans lui.

Les deux méthodes classent différemment, avec une corrélation de rang de 0,44. Un tronçon très fréquenté dans un réseau dense se contourne, tandis qu'un tronçon peu fréquenté devient indispensable quand il constitue le seul franchissement d'un obstacle naturel. La charge ne mesure donc pas la criticité.

## Choix du seuil d'accessibilité

Le seuil de 120 minutes, courant en planification, ne discrimine presque rien ici : la couverture initiale atteint déjà 94 %, et fermer 77 hôpitaux sur 198 ne la fait passer que de 94,1 % à 94,0 %.

Le seuil principal est donc de 60 minutes, plus pertinent pour les urgences obstétricales, en particulier les hémorragies du post-partum, qui tuent vite sans prise en charge. Les résultats à 30 et 120 minutes restent dans les tableaux, pour montrer la sensibilité au seuil.

## Résultats

### La définition des hôpitaux change fortement la couverture estimée

La classification des structures dans OpenStreetMap est la première source d'incertitude sur l'offre. L'étiquette `amenity=hospital` couvre 1 185 points en Haïti, contre 198 pour `healthcare=hospital`.

L'écart tient en partie à la cartographie d'urgence de 2010, où des dispensaires et des centres de santé ont été saisis comme hôpitaux. L'étiquette `healthcare=hospital`, plus récente et mieux tenue, donne une définition plus restrictive.

| Définition de l'offre          | Structures | À 30 min | À 60 min   | À 120 min | Temps médian |
| ------------------------------ | ---------- | -------- | ---------- | --------- | ------------ |
| SONUC, étiquettes concordantes | 198        | 56,9 %   | **78,1 %** | 94,1 %    | 19 min       |
| SONUC élargi                   | 1 184      | 90,5 %   | 94,7 %     | 95,7 %    | 6 min        |
| Toute offre de soins           | 1 419      | 90,7 %   | 94,8 %     | 95,9 %    | 5 min        |

À 60 minutes, la couverture va de 78,1 % avec la définition restrictive à 94,7 % avec la définition élargie. À 30 minutes, l'écart atteint 33,6 points. L'analyse principale retient la définition restrictive et conserve les autres estimations, pour que l'incertitude reste visible.

Sous cette définition, 4,8 % de la demande n'est reliée à aucun hôpital par la route. Trois communes n'ont même pas de temps médian, faute d'un seul SONUC atteignable depuis leur sous-réseau : l'Île-à-Vache et La Tortue, qui sont insulaires, et Grand-Boucan dans les Nippes. Douze communes en tout n'ont aucune part de leur demande à moins d'une heure d'un hôpital.

### Les pertes d'accessibilité se concentrent sur quelques tronçons

Le classement par perte mesurée fait ressortir quatre tronçons de la RN1 à Saint-Marc et quatre tronçons de la RN3 à Mirebalais.

Le tronçon le plus lourd fait basculer à lui seul 19 689 femmes au-delà d'une heure, soit 85 % de la perte totale des quinze coupures testées. À partir du sixième tronçon, chaque coupure supplémentaire n'ajoute presque rien.

La vulnérabilité du réseau n'est donc pas répartie uniformément : elle se loge dans les segments pour lesquels il existe peu d'itinéraires de rechange.

### Fermetures de structures et coupures de routes ne produisent pas le même effet

| Scénario                             | À 30 min   | À 60 min | Médiane    | Demande décrochée |
| ------------------------------------ | ---------- | -------- | ---------- | ----------------- |
| Référence                            | 56,9 %     | 78,1 %   | 19 min     | —                 |
| A. 10 points de contrôle             | 56,6 %     | 77,3 %   | 19 min     | 23 131            |
| B. Encerclement de la ZMPP           | 55,8 %     | 76,3 %   | 20 min     | 57 056            |
| C. A et B cumulés                    | 55,4 %     | 75,6 %   | 20 min     | 80 186            |
| D. Fermeture des hôpitaux de la ZMPP | **45,4 %** | 77,5 %   | **32 min** | 18 235            |
| E. C et D cumulés                    | 41,3 %     | 74,4 %   | 33 min     | **118 721**       |

Fermer les 77 hôpitaux de l'aire métropolitaine fait chuter la couverture à 30 minutes de 56,9 % à 45,4 % et porte le temps médian de 19 à 32 minutes. À 60 minutes, la couverture reste pourtant proche de la référence, à 77,5 %.

Les scénarios de réseau font l'inverse. Sous l'encerclement de la ZMPP, la part de la demande sans aucun accès routier à un hôpital passe de 4,8 % à 5,9 % : des femmes perdent tout itinéraire, pas seulement des minutes.

D'où l'intérêt de conserver plusieurs seuils. Le seul indicateur à 60 minutes ne verrait pas l'allongement des trajets provoqué par les fermetures, qu'un seuil plus court met en évidence.

Dans le scénario combiné, 118 721 femmes de 15 à 49 ans passent au-delà d'une heure. Les pertes suivent le corridor de la RN1 et touchent surtout Gressier (72 % de la demande communale), Croix-des-Bouquets (60 %), Cabaret (56 %) et Ganthier (55 %).

## Limites de l'analyse

### Les points de contrôle sont des scénarios, pas des observations

Les données ACLED diffusées sur HDX sont agrégées au mois et à la commune, sans coordonnées d'incident. Les points de contrôle des simulations viennent donc d'une règle de placement explicite et ne localisent aucun barrage observé.

La distinction commande la lecture des cartes : les scénarios représentent des configurations hypothétiques du réseau, pas une cartographie des barrages effectifs. Une version d'ACLED avec coordonnées s'intégrerait à la même chaîne en remplaçant le seul fichier de points.

### La qualification SONU reste un proxy

OpenStreetMap localise les structures mais ne dit rien de leur capacité à assurer une prise en charge obstétricale d'urgence : ni bloc opératoire fonctionnel, ni réserve de sang, ni équipe de nuit.

Les couvertures mesurent donc l'accessibilité géographique à des structures étiquetées hôpitaux, et non l'accès effectif à des soins obstétricaux d'urgence.

### Le réseau est traité comme non orienté

Les sens uniques ne sont pas pris en compte. À l'échelle des déplacements intercommunaux étudiés ici, cette simplification pèse moins que l'incertitude sur les vitesses, mais elle reste une limite, d'autant que l'attribut `oneway` est inégalement renseigné dans l'OSM haïtien.

### La capacité des structures n'est pas modélisée

L'analyse mesure le temps d'accès à une structure, pas sa capacité à accueillir une patiente de plus. Un établissement à 20 minutes compte comme accessible quels que soient ses lits libres, son personnel ou la demande simultanée. Les résultats décrivent une accessibilité spatiale et temporelle, sans contrainte de capacité.

## Reproduction

```bash
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
python run_all.py
```

Sources déjà téléchargées, la chaîne complète prend une vingtaine de minutes. L'étape 4 en représente la plus grande part, jusqu'à une dizaine de minutes au premier lancement, car elle recalcule l'accessibilité nationale pour chacun des 150 tronçons candidats ; elle descend à trois minutes quand les couches sont encore en cache disque.

`python run_all.py --depuis 3` reprend après la construction du graphe. `--etape 4` relance les seuls scénarios.

## Arborescence

```text
data/raw/                  sources téléchargées, non versionnées
data/processed/            couches intermédiaires (graphe, cellules, scénarios)
src/config.py              paramètres de modélisation et justification
src/acces.py               calcul du graphe, Dijkstra multi-sources et flux
src/p01 à p05              cinq étapes de la chaîne
outputs/figures/           7 cartes et graphiques
outputs/tables/            8 tableaux de résultats
outputs/carte_interactive.html
notebooks/analyse.ipynb
```
---

# Access to Emergency Obstetric Care under Road Blockage, Haiti

## Context

Santé Commune Initiative (SCI) is a fictional NGO specializing in reproductive health. In an earlier project, it identified Haitian communes where a sexual and reproductive health programme could be concentrated, based on potential demand and the density of health facilities. Two years later, the organization wants to extend that targeting to whether women can actually reach the facilities.

Naming the right communes is not enough. A woman facing an obstetric emergency still has to reach a facility able to treat her, which assumes passable roads and open hospitals.

The commissioning organization and its mandate are fictional. All datasets are real and publicly available.

## Question

What share of Haitian obstetric demand is located within one hour of a hospital, and how does this accessibility change when road segments are blocked or health facilities close?

## Data

| Source              | Dataset                                                           | Level                                                | License     |
| ------------------- | ----------------------------------------------------------------- | ---------------------------------------------------- | ----------- |
| HOT / OpenStreetMap | Road network                                                      | 133,449 segments, including 97,650 routable segments | ODbL        |
| WorldPop            | Gridded population 2020, constrained and adjusted to UN estimates | 100 m, aggregated to 1 km                            | CC BY 4.0   |
| OCHA COD-AB         | Administrative boundaries                                         | 140 communes                                         | CC BY-IGO   |
| OCHA COD-PS         | 2024 population by sex and age                                    | Commune                                              | CC BY-IGO   |
| HOT / OpenStreetMap | Health facilities                                                 | 2,073 points                                         | ODbL        |
| ACLED via HDX       | Violence against civilians                                        | Commune, monthly                                     | ACLED terms |

Sources, URLs, and data limitations are detailed in `data/README_data.md`.

## Method

### Building the road network

Each pair of consecutive points in an OSM polyline becomes an edge. Coordinates are rounded to the nearest metre before duplicate vertices are removed, which restores the network topology: intersecting segments then share the same node. The graph contains 1.33 million nodes, 1.36 million edges, and 36,755 km of roads.

Travel speeds represent effective door-to-door speeds and are deliberately lower than posted limits. Within the Port-au-Prince metropolitan area they are reduced by 45 % for congestion. The values and their justification are in `src/config.py`.

### Estimating demand

WorldPop data are aggregated into cells of roughly 1 km, then adjusted commune by commune to the 2024 COD-PS population estimates. WorldPop supplies the spatial distribution, COD-PS the commune totals.

Each cell is weighted by the commune-level share of women aged 15 to 49. In total, 8,259 cells carry 11.9 million inhabitants and 3.25 million women of reproductive age.

### Calculating accessibility

A multi-source Dijkstra starts from all selected facilities at once. Because the graph is undirected, a single traversal gives the travel time from every node to the nearest facility.

The link between a cell centre and the nearest road node is costed at 4 km/h with a detour factor of 1.3, which accounts for movement outside the network.

### Identifying critical road segments

Criticality is assessed in two stages. A first pass shortlists segments by the demand routed over them along fastest paths. A second pass measures directly the loss of accessibility their removal causes.

That direct assessment covers 150 shortlisted segments separated by at least 3 km. For each one, national accessibility is recalculated without it.

The two rankings differ, with a rank correlation of 0.44. A heavily used road in a dense network can be bypassed, while a lightly used segment becomes essential when it is the only crossing over a physical barrier. Traffic volume therefore does not measure criticality.

## Choice of accessibility threshold

The 120-minute threshold, common in planning work, discriminates almost nothing here: initial coverage already reaches 94 %, and closing 77 of the 198 hospitals moves it only from 94.1 % to 94.0 %.

The main threshold is therefore 60 minutes, which is also more relevant to emergency obstetric care, particularly postpartum haemorrhage, which kills quickly without treatment. Results at 30 and 120 minutes remain in the tables to show sensitivity to the threshold.

## Results

### The definition of hospitals substantially changes estimated coverage

Facility classification in OpenStreetMap is the first source of uncertainty about supply. The `amenity=hospital` tag covers 1,185 points in Haiti, against 198 for `healthcare=hospital`.

The gap partly reflects the 2010 emergency mapping effort, when dispensaries and health centres were also recorded as hospitals. The more recent and better maintained `healthcare=hospital` tag gives a stricter definition.

| Supply definition     | Facilities | Within 30 min | Within 60 min | Within 120 min | Median time |
| --------------------- | ---------- | ------------- | ------------- | -------------- | ----------- |
| SONUC, matching tags  | 198        | 56.9 %        | **78.1 %**    | 94.1 %         | 19 min      |
| Expanded SONUC        | 1,184      | 90.5 %        | 94.7 %        | 95.7 %         | 6 min       |
| All health facilities | 1,419      | 90.7 %        | 94.8 %        | 95.9 %         | 5 min       |

At 60 minutes, coverage ranges from 78.1 % under the restrictive definition to 94.7 % under the expanded one. At 30 minutes the gap reaches 33.6 percentage points. The main analysis uses the restrictive definition and keeps the alternatives, so that the uncertainty stays visible.

Under that definition, 4.8 % of demand has no road connection to any hospital. Three communes have no median travel time at all, because no SONUC is reachable from their sub-network: Île-à-Vache and La Tortue, which are islands, and Grand-Boucan in Nippes. Twelve communes in total have no share of their demand within one hour of a hospital.

### Accessibility losses are concentrated on a small number of segments

Ranking by measured loss brings out four segments of RN1 in Saint-Marc and four segments of RN3 in Mirebalais.

The heaviest segment alone moves 19,689 women beyond the one-hour threshold, or 85 % of the total loss across the fifteen roadblocks tested. From the sixth segment onward, each additional cut adds almost nothing.

Network vulnerability is therefore not evenly spread: it sits in the segments with few alternative routes.

### Facility closures and road cuts do not produce the same effect

| Scenario                     | Within 30 min | Within 60 min | Median     | Demand losing access |
| ---------------------------- | ------------- | ------------- | ---------- | -------------------- |
| Reference                    | 56.9 %        | 78.1 %        | 19 min     | —                    |
| A. 10 checkpoints            | 56.6 %        | 77.3 %        | 19 min     | 23,131               |
| B. ZMPP encirclement         | 55.8 %        | 76.3 %        | 20 min     | 57,056               |
| C. A and B combined          | 55.4 %        | 75.6 %        | 20 min     | 80,186               |
| D. Closure of ZMPP hospitals | **45.4 %**    | 77.5 %        | **32 min** | 18,235               |
| E. C and D combined          | 41.3 %        | 74.4 %        | 33 min     | **118,721**          |

Closing the 77 hospitals of the metropolitan area cuts coverage at 30 minutes from 56.9 % to 45.4 % and raises median travel time from 19 to 32 minutes. At 60 minutes, coverage still sits close to the reference level, at 77.5 %.

The network scenarios do the opposite. Under the ZMPP encirclement, the share of demand with no road access to any hospital rises from 4.8 % to 5.9 %: those women lose a route, not just minutes.

Hence the value of keeping several thresholds. A single 60-minute indicator would miss the longer journeys caused by closures, which a shorter threshold makes visible.

Under the combined scenario, 118,721 women aged 15 to 49 move beyond the one-hour threshold. The losses follow the RN1 corridor and fall mainly on Gressier (72 % of communal demand), Croix-des-Bouquets (60 %), Cabaret (56 %), and Ganthier (55 %).

## Limitations

### Checkpoints are scenarios, not observations

The ACLED data distributed through HDX are aggregated to commune and month, with no incident coordinates. The checkpoints used in the simulations therefore come from an explicit placement rule and locate no observed roadblock.

The distinction governs how the maps should be read: the scenarios represent hypothetical network configurations, not a map of actual roadblocks. A version of ACLED with coordinates would fit the same workflow by replacing the point file alone.

### The SONUC classification is a proxy

OpenStreetMap locates facilities but says nothing about their capacity to provide emergency obstetric care: no functional operating theatre, no blood supply, no night team can be verified.

Coverage figures therefore measure geographic accessibility to facilities tagged as hospitals, not effective access to emergency obstetric care.

### The network is treated as undirected

One-way streets are not modelled. At the scale of the inter-communal journeys studied here, this simplification matters less than the uncertainty on travel speeds, but it remains a limitation, particularly because the `oneway` attribute is unevenly recorded in Haitian OSM data.

### Facility capacity is not modelled

The analysis measures travel time to a facility, not its capacity to take one more patient. A facility 20 minutes away counts as accessible whatever its free beds, staffing, or concurrent demand. The results describe spatial and travel-time accessibility, with no capacity constraint.

## Reproduction

```bash
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
python run_all.py
```

With the source data already downloaded, the full workflow runs in about twenty minutes. Step 4 accounts for most of it, up to ten minutes on a first run, because it recalculates national accessibility for each of the 150 candidate segments; it drops to three minutes when the layers are still in the disk cache.

`python run_all.py --depuis 3` resumes after graph construction. `--etape 4` reruns the scenarios only.

## Directory structure

```text
data/raw/                  downloaded sources, not versioned
data/processed/            intermediate layers (graph, cells, scenarios)
src/config.py              modelling parameters and justification
src/acces.py               graph, multi-source Dijkstra, and flow calculations
src/p01 to p05             five stages of the workflow
outputs/figures/           7 maps and figures
outputs/tables/            8 results tables
outputs/carte_interactive.html
notebooks/analyse.ipynb
```
