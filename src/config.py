"""
Paramètres partagés du projet « Accès aux SONU sous blocage routier, Haïti ».

Tout paramètre de modélisation est déclaré ici, jamais en dur dans les scripts.
Chaque valeur est accompagnée de sa justification, parce qu'un paramètre non
justifié est un paramètre non défendable devant un bailleur.
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

# Les données sources sont en WGS 84 géographique.
CRS_SOURCE = "EPSG:4326"

# Haïti tient entièrement dans le fuseau UTM 18 Nord. Toute mesure de distance,
# de longueur d'arête et de rayon de rattachement se fait dans ce système, en
# mètres. Calculer une longueur en degrés décimaux serait une erreur : un degré
# de longitude vaut environ 108 km à l'équateur et 0 km au pôle.
CRS_METRIQUE = "EPSG:32618"

# --------------------------------------------------------------------------
# Réseau routier : vitesses de parcours
# --------------------------------------------------------------------------

# Vitesses moyennes de parcours en km/h, par classe OpenStreetMap.
#
# Ce ne sont pas des vitesses réglementaires mais des vitesses effectives de
# porte à porte, volontairement basses. Le réseau haïtien combine revêtement
# dégradé, franchissements de ravines non bitumés et traversées d'agglomération
# sans voie réservée. Retenir les vitesses réglementaires produirait des
# isochrones optimistes de 30 à 50 %, ce qui est le biais classique des analyses
# d'accessibilité fondées sur OSM.
#
# Ordre de grandeur retenu : un trajet Port-au-Prince - Saint-Marc (environ
# 95 km par la RN1) ressort autour de 2 h, ce qui correspond aux temps de
# parcours couramment rapportés hors période de blocage.
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

# Classes OSM exclues du graphe carrossable : un transfert obstétrical ne passe
# pas par un sentier piéton ou un escalier.
CLASSES_EXCLUES = {
    "footway", "path", "pedestrian", "steps", "cycleway", "bridleway",
    "corridor", "platform", "raceway", "construction", "proposed",
    "escape", "busway", "elevator",
}

# Facteur de congestion appliqué aux vitesses à l'intérieur de l'aire
# métropolitaine de Port-au-Prince. Une valeur de 0,55 signifie que l'on retient
# 55 % de la vitesse de classe. La ZMPP cumule densité, marchés de rue occupant
# la chaussée et carrefours non régulés ; les vitesses observées en journée y
# tombent couramment sous 15 km/h sur les axes secondaires.
FACTEUR_CONGESTION_ZMPP = 0.55

# --------------------------------------------------------------------------
# Rattachement de la demande au réseau
# --------------------------------------------------------------------------

# Vitesse du segment terminal, entre le centre de la cellule de population et le
# nœud routier le plus proche. Ce segment est parcouru à pied ou en moto-taxi
# sur piste ; 4 km/h est la vitesse de marche standard en terrain non plat.
VITESSE_ACCES_KMH = 4.0

# Les déplacements réels ne suivent pas la ligne droite. La distance euclidienne
# du centre de cellule au nœud routier est multipliée par ce facteur de détour.
FACTEUR_DETOUR = 1.3

# Au-delà de cette distance à vol d'oiseau, on considère que la cellule n'est pas
# rattachable au réseau carrossable et son temps de trajet est marqué comme non
# atteignable plutôt que gonflé artificiellement par une très longue marche.
DISTANCE_MAX_RATTACHEMENT_M = 10_000

# --------------------------------------------------------------------------
# Offre de soins
# --------------------------------------------------------------------------

# OpenStreetMap ne porte aucun attribut décrivant la capacité obstétricale
# réelle d'une structure. La qualification ci-dessous est un proxy construit sur
# les attributs disponibles, et non une donnée observée.
#
# Le jeu haïtien impose une précaution supplémentaire. L'étiquette
# `amenity=hospital` y est posée sur 1 185 points, un chiffre sans rapport avec
# le parc hospitalier réel du pays : c'est une séquelle de la cartographie
# d'urgence de 2010, où dispensaires et centres de santé ont été saisis comme
# hôpitaux. L'étiquette `healthcare=hospital`, plus tardive et mieux tenue, n'en
# retient que 198, ordre de grandeur cohérent avec le parc recensé par le
# ministère de la Santé publique et de la Population.
#
# Trois niveaux sont donc distingués, et l'analyse est menée sur deux bornes
# plutôt que sur un chiffre unique.
#
#   SONUC          les deux étiquettes concordent : capacité chirurgicale
#                  présumée. Borne basse de l'offre.
#   HOPITAL_NC     `amenity=hospital` sans confirmation par `healthcare`.
#                  Un établissement existe, sa nature reste incertaine.
#   SONUB          cliniques, cabinets, centres de santé : première ligne,
#                  sans césarienne.
TAG_SONUC = "hospital"
TAGS_SONUB = {"clinic", "doctors", "doctor", "health_post", "health_centre", "centre", "yes"}

# Points de santé sans rôle possible dans une urgence obstétricale : ils sont
# écartés du périmètre, quel que soit leur niveau.
TAGS_HORS_PERIMETRE = {
    "pharmacy", "dentist", "laboratory", "blood_donation", "physiotherapist",
    "psychotherapist", "massage_therapy", "counselling", "veterinary",
    "place_of_worship", "optometrist", "alternative",
}

# --------------------------------------------------------------------------
# Seuils d'accessibilité
# --------------------------------------------------------------------------

# 120 minutes est le seuil de planification usuel dans la littérature sur l'accès
# aux SONU complets. Il n'est pas retenu ici comme indicateur principal, pour une
# raison mesurée sur ces données : la couverture de départ y atteint 94 %, si
# bien que l'indicateur ne bouge presque plus quoi qu'on simule. Un indicateur
# saturé ne mesure rien.
#
# Le seuil de référence est donc fixé à 60 minutes. Ce choix est aussi le mieux
# fondé cliniquement : l'hémorragie du post-partum, première cause de mortalité
# maternelle, tue en une à deux heures sans prise en charge, et la césarienne
# d'urgence se compte en dizaines de minutes. Les deux autres seuils restent
# publiés pour permettre la comparaison avec les études existantes.
SEUILS_MINUTES = (30, 60, 120)
SEUIL_REFERENCE = 60

# --------------------------------------------------------------------------
# Population
# --------------------------------------------------------------------------

# WorldPop est diffusé à 3 secondes d'arc, soit environ 100 m. Router depuis
# chaque cellule de 100 m serait inutilement coûteux et faussement précis au
# regard de la résolution du réseau routier. Les cellules sont agrégées par
# blocs de FACTEUR_AGREGATION x FACTEUR_AGREGATION, soit environ 1 km.
FACTEUR_AGREGATION = 10

# Une cellule agrégée portant moins de cet effectif est écartée : elle
# représente du bruit de désagrégation, pas un lieu de vie.
POP_MIN_CELLULE = 10.0

# --------------------------------------------------------------------------
# Scénarios de blocage
# --------------------------------------------------------------------------

# Fenêtre ACLED retenue pour mesurer l'intensité des violences contre les
# civils, en mois précédant la date d'extraction du jeu.
FENETRE_ACLED_MOIS = 24

# Les communes exposées sont celles qui, classées par nombre d'événements
# décroissant, cumulent cette part du total national.
#
# Un seuil par quantile a d'abord été essayé, et écarté : la distribution est si
# concentrée que le troisième quartile vaut zéro événement, si bien que le
# critère revenait à retenir toute commune ayant connu un seul incident en deux
# ans. Le critère par part cumulée suit la concentration réelle du phénomène au
# lieu de la contredire.
PART_EVENEMENTS_EXPOSEES = 0.80

# Nombre de points de contrôle posés dans le scénario diffus.
N_POINTS_CONTROLE = 10

# Nombre de tronçons présélectionnés sur leur charge, puis évalués un par un par
# recalcul complet de l'accessibilité.
#
# Ce double filtre corrige une erreur de raisonnement tentante : le tronçon le
# plus fréquenté n'est pas le plus critique. En zone dense, une artère très
# chargée se contourne par le maillage voisin, et sa coupure ne coûte que
# quelques minutes. Ce qui fait mal, c'est le tronçon sans alternative, souvent
# modestement fréquenté. Seul un recalcul le révèle ; la charge ne sert qu'à
# ramener le champ des candidats à une taille calculable.
N_CANDIDATS_EVALUES = 150

# Deux points de contrôle ne peuvent pas être posés à moins de cette distance
# l'un de l'autre. Sans cette contrainte, l'algorithme sélectionne vingt arêtes
# consécutives du même axe, ce qui décrit un seul barrage et non vingt.
ESPACEMENT_MIN_CONTROLES_M = 3_000

# Communes composant l'aire métropolitaine de Port-au-Prince (ZMPP).
# Codes ADM2 OCHA.
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

# Les couleurs et les réglages matplotlib sont dans src/style.py, qui documente
# la validation de la palette. Seule la résolution d'export vit ici.
DPI_FIGURES = 200
