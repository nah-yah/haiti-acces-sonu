"""
Paramètres partagés du projet « Accès aux SONU sous blocage routier, Haïti ».

Tout paramètre de modélisation est déclaré ici, jamais en dur dans les scripts.
"""

from pathlib import Path

# --------------------------------------------------------------------------
# Arborescence
# --------------------------------------------------------------------------

RACINE = Path(__file__).resolve().parents[1]
DATA_BRUT = RACINE / "data" / "raw"
DATA_TRAITE = RACINE / "data" / "processed"
SORTIES = RACINE / "outputs"
FIGURES = SORTIES / "figures"
TABLEAUX = SORTIES / "tables"

for _d in (DATA_TRAITE, FIGURES, TABLEAUX):
    _d.mkdir(parents=True, exist_ok=True)

# --------------------------------------------------------------------------
# Systèmes de coordonnées
# --------------------------------------------------------------------------

CRS_SOURCE = "EPSG:4326"

# Haïti tient dans le fuseau UTM 18 Nord. Toute mesure de distance se fait dans
# ce système, en mètres, jamais en degrés décimaux.
CRS_METRIQUE = "EPSG:32618"

# --------------------------------------------------------------------------
# Réseau routier : vitesses de parcours
# --------------------------------------------------------------------------

# Vitesses effectives de porte à porte en km/h, par classe OSM, volontairement
# basses : le réseau haïtien combine revêtement dégradé, ravines non bitumées et
# traversées d'agglomération. Les vitesses réglementaires donneraient des
# isochrones optimistes de 30 à 50 %.
VITESSES_KMH = {
    "motorway": 70,
    "motorway_link": 45,
    "trunk": 60,
    "trunk_link": 40,
    "primary": 50,
    "primary_link": 35,
    "secondary": 40,
    "secondary_link": 30,
    "tertiary": 30,
    "tertiary_link": 25,
    "unclassified": 25,
    "residential": 20,
    "living_street": 12,
    "service": 12,
    "road": 25,
    "track": 12,
}

# Classes non carrossables : un transfert obstétrical ne passe pas par un
# sentier ni un escalier.
CLASSES_EXCLUES = {
    "footway", "path", "pedestrian", "steps", "cycleway", "bridleway",
    "corridor", "platform", "raceway", "construction", "proposed",
    "escape", "busway", "elevator",
}

# Part de la vitesse de classe retenue dans l'aire métropolitaine de
# Port-au-Prince, où les vitesses observées tombent sous 15 km/h en journée.
FACTEUR_CONGESTION_ZMPP = 0.55

# --------------------------------------------------------------------------
# Rattachement de la demande au réseau
# --------------------------------------------------------------------------

# Segment terminal, du centre de cellule au nœud routier : marche ou moto-taxi
# sur piste.
VITESSE_ACCES_KMH = 4.0

# Les déplacements réels ne suivent pas la ligne droite.
FACTEUR_DETOUR = 1.3

# Au-delà, la cellule est déclarée non rattachable plutôt que dotée d'un temps
# gonflé par une marche de plusieurs heures.
DISTANCE_MAX_RATTACHEMENT_M = 10_000

# --------------------------------------------------------------------------
# Offre de soins
# --------------------------------------------------------------------------

# OSM ne porte aucun attribut de capacité obstétricale : la qualification
# ci-dessous est un proxy, pas une donnée observée.
#
# Le jeu haïtien impose une précaution. `amenity=hospital` est posé sur 1 185
# points, séquelle de la cartographie d'urgence de 2010 où dispensaires et
# centres de santé ont été saisis comme hôpitaux. `healthcare=hospital`, plus
# tardif, n'en retient que 198, ordre de grandeur cohérent avec le parc du MSPP.
# D'où trois niveaux, et une analyse menée sur deux bornes :
#
#   SONUC        les deux étiquettes concordent, capacité chirurgicale présumée
#   HOPITAL_NC   `amenity=hospital` seul, nature de l'établissement incertaine
#   SONUB        cliniques et centres de santé, première ligne sans césarienne
TAG_SONUC = "hospital"
TAGS_SONUB = {"clinic", "doctors", "doctor", "health_post", "health_centre", "centre", "yes"}

# Points de santé sans rôle possible dans une urgence obstétricale.
TAGS_HORS_PERIMETRE = {
    "pharmacy", "dentist", "laboratory", "blood_donation", "physiotherapist",
    "psychotherapist", "massage_therapy", "counselling", "veterinary",
    "place_of_worship", "optometrist", "alternative",
}

# --------------------------------------------------------------------------
# Seuils d'accessibilité
# --------------------------------------------------------------------------

# Le seuil de 120 minutes, usuel dans la littérature, est publié mais pas retenu
# comme indicateur principal : la couverture de départ y atteint 94 %, si bien
# qu'il ne bouge presque plus quoi qu'on simule. 60 minutes est aussi le mieux
# fondé cliniquement, l'hémorragie du post-partum tuant en une à deux heures.
SEUILS_MINUTES = (30, 60, 120)
SEUIL_REFERENCE = 60

# --------------------------------------------------------------------------
# Population
# --------------------------------------------------------------------------

# WorldPop est diffusé à environ 100 m. Les cellules sont agrégées par blocs de
# FACTEUR_AGREGATION de côté, soit environ 1 km : router depuis chaque cellule
# de 100 m serait coûteux et faussement précis au regard du réseau routier.
FACTEUR_AGREGATION = 10

# En deçà, une cellule agrégée relève du bruit de désagrégation.
POP_MIN_CELLULE = 10.0

# --------------------------------------------------------------------------
# Scénarios de blocage
# --------------------------------------------------------------------------

# Fenêtre ACLED, en mois précédant la date d'extraction du jeu.
FENETRE_ACLED_MOIS = 24

# Les communes exposées sont celles qui, classées par nombre d'événements
# décroissant, cumulent cette part du total national. Un seuil par quantile a
# été écarté : la distribution est si concentrée que le troisième quartile vaut
# zéro événement.
PART_EVENEMENTS_EXPOSEES = 0.80

# Nombre de points de contrôle posés dans le scénario diffus.
N_POINTS_CONTROLE = 10

# Tronçons présélectionnés sur leur charge, puis évalués un par un par recalcul
# complet. Le tronçon le plus fréquenté n'est pas le plus critique : en zone
# dense une artère chargée se contourne. La charge ne sert qu'à ramener le champ
# des candidats à une taille calculable.
N_CANDIDATS_EVALUES = 150

# Espacement minimal entre deux points de contrôle. Sans cette contrainte,
# l'algorithme retient vingt arêtes consécutives du même axe, ce qui décrit un
# seul barrage.
ESPACEMENT_MIN_CONTROLES_M = 3_000

# Communes de l'aire métropolitaine de Port-au-Prince (ZMPP), codes ADM2 OCHA.
PCODES_ZMPP = [
    "HT0111",  # Port-au-Prince
    "HT0112",  # Delmas
    "HT0113",  # Carrefour
    "HT0114",  # Petion-Ville
    "HT0115",  # Kenscoff
    "HT0116",  # Gressier
    "HT0117",  # Tabarre
    "HT0121",  # Croix-des-Bouquets
    "HT0131",  # Cite Soleil
]

# --------------------------------------------------------------------------
# Rendu
# --------------------------------------------------------------------------

# Couleurs et réglages matplotlib : voir src/style.py.
DPI_FIGURES = 200
