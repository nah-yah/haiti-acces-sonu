# Données du projet

Aucun fichier de `data/` n'est versionné : la chaîne les reconstruit à
l'identique depuis les catalogues d'origine.

```
python src/telecharger_donnees.py
```

## Sources

| Source | Jeu | Fichier attendu | Catalogue | Licence |
|---|---|---|---|---|
| HOT / OpenStreetMap | Réseau routier d'Haïti | `hotosm_hti_roads_gpkg.zip` puis `roads.gpkg` | [HDX](https://data.humdata.org/dataset/hotosm_hti_roads) | ODbL |
| WorldPop | Population maillée 100 m, 2020, contrainte et ajustée ONU | `hti_ppp_2020_UNadj_constrained.tif` | [WorldPop](https://hub.worldpop.org/geodata/summary?id=39527) | CC BY 4.0 |
| OCHA COD-AB | Limites administratives, niveaux 0 à 2 | `hti_admin_boundaries/` | [HDX](https://data.humdata.org/dataset/cod-ab-hti) | CC BY-IGO |
| OCHA COD-PS | Population communale 2024 par sexe et âge | `hti_admpop_adm2_2024.csv` | [HDX](https://data.humdata.org/dataset/cod-ps-hti) | CC BY-IGO |
| HOT / OpenStreetMap | Structures de santé | `hti_health_facilities/` | [HDX](https://data.humdata.org/dataset/hotosm_hti_health_facilities) | ODbL |
| ACLED via HDX | Événements de violence contre les civils, par commune et par mois | `acled_civilian_targeting_adm2.xlsx` | [HDX](https://data.humdata.org/dataset/haiti-acled-conflict-data) | Conditions ACLED |

Les quatre derniers jeux sont repris tels quels du projet QGIS
`geospatial-ssr-haiti-2024`, afin que les deux analyses partagent exactement le
même découpage communal et le même millésime de population. Le script de
téléchargement signale ceux qui manquent et rappelle où les prendre.

## Trois limites qui changent la lecture des résultats

### 1. OpenStreetMap ne dit pas ce qu'une structure sait faire

Le jeu des structures de santé porte les étiquettes `amenity` et `healthcare`,
qui décrivent un type d'établissement, jamais une capacité clinique. Aucun
attribut n'indique si un bloc opératoire fonctionne, si du sang est disponible,
si une équipe est présente la nuit.

La qualification employée ici est donc un proxy assumé : les hôpitaux sont
traités comme des SONU complets, les centres de santé et cliniques comme des
SONU de base. La couverture réelle en soins obstétricaux d'urgence est
nécessairement **inférieure** à celle que produit ce calcul, puisqu'une partie
des points classés « hôpital » n'assure pas de césarienne 24 heures sur 24. Les
résultats se lisent comme une borne supérieure de l'accessibilité, pas comme une
mesure de l'offre effective.

Une évaluation opérationnelle demanderait la liste HeRAMS ou l'annuaire du
ministère de la Santé publique et de la Population, qui ne sont pas des données
ouvertes.

### 2. ACLED est agrégé, il ne localise aucun barrage

Le jeu ACLED diffusé sur HDX donne, par commune et par mois, un nombre
d'événements et de victimes. Il ne contient aucune coordonnée. Il permet donc de
dire quelles communes sont les plus exposées, jamais où se tient un point de
contrôle.

Les points de contrôle du scénario A sont par conséquent **construits par le
modèle** : ce sont les tronçons qui portent le plus de demande obstétricale,
parmi ceux situés dans les communes du quartier supérieur de violences, espacés
d'au moins trois kilomètres. La règle est explicite et reproductible, mais son
produit reste un scénario. La carte des points de contrôle ne doit jamais être
présentée, ni lue, comme une carte de barrages existants.

L'accès aux événements géolocalisés d'ACLED suppose une clé d'interface obtenue
auprès d'ACLED. Avec cette clé, la même chaîne accepterait des positions
observées à la place des positions modélisées, sans autre changement que la
source du fichier de points.

### 3. Deux millésimes de population, recalés l'un sur l'autre

WorldPop décrit 2020, le fichier COD-PS décrit 2024. La forme spatiale de la
distribution vient du premier, le niveau vient du second : les cellules d'une
commune sont multipliées par un facteur unique pour que leur somme reproduise
l'effectif communal 2024. Le facteur appliqué est enregistré dans les sorties.
Un facteur très éloigné de 1 signale une commune où les deux sources divergent,
souvent un quartier de la zone métropolitaine touché par les déplacements
internes récents.

## Volumétrie

Environ 55 Mo téléchargés, 70 Mo après extraction du GeoPackage routier. Les
couches intermédiaires écrites dans `data/processed/` occupent environ 120 Mo,
dont l'essentiel pour le graphe routier.
