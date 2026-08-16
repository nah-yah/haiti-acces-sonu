"""
Étape 2 : construction du graphe routier pondéré en temps de parcours.

Le graphe est construit sommet par sommet à partir des géométries OSM. Chaque
couple de points consécutifs d'une polyligne devient une arête. Les coordonnées
sont arrondies au mètre avant d'être dédoublonnées : c'est cet arrondi qui
recrée la topologie, puisque deux tronçons qui se croisent dans OSM partagent
exactement le même nœud.

Le graphe est traité comme non orienté. Les sens uniques sont ignorés, choix
assumé : à l'échelle d'un transfert obstétrical inter-communal, l'erreur induite
est inférieure à l'incertitude sur les vitesses, et l'attribut oneway est très
inégalement renseigné dans OSM Haïti.

Sortie : data/processed/graphe.npz
"""

from __future__ import annotations

import sys
from pathlib import Path

import geopandas as gpd
import numpy as np
import shapely

sys.path.insert(0, str(Path(__file__).resolve().parent))

from config import (  # noqa: E402
    CLASSES_EXCLUES,
    CRS_METRIQUE,
    CRS_SOURCE,
    DATA_BRUT,
    DATA_TRAITE,
    FACTEUR_CONGESTION_ZMPP,
    TABLEAUX,
    VITESSES_KMH,
)
from utils import etape, exiger, log, trouver_colonne  # noqa: E402


def charger_routes() -> gpd.GeoDataFrame:
    chemin = DATA_BRUT / "roads.gpkg"
    exiger(
        chemin.exists(),
        "roads.gpkg absent. Lancer d'abord python src/telecharger_donnees.py",
    )

    routes = gpd.read_file(chemin)
    col_classe = trouver_colonne(routes.columns, "highway")
    routes = routes.rename(columns={col_classe: "classe"})
    routes["classe"] = routes["classe"].fillna("unclassified").astype(str).str.lower()

    avant = len(routes)
    routes = routes[~routes["classe"].isin(CLASSES_EXCLUES)]
    routes = routes[routes["classe"].isin(VITESSES_KMH)]
    log(f"tronçons : {avant} lus, {len(routes)} carrossables retenus")

    repartition = routes["classe"].value_counts()
    log("répartition par classe :\n" + repartition.to_string())
    repartition.rename("troncons").to_csv(TABLEAUX / "02_classes_routieres.csv")

    if routes.crs is None:
        routes = routes.set_crs(CRS_SOURCE)
    routes = routes.to_crs(CRS_METRIQUE)

    # Une polyligne multiple est décomposée : le graphe se construit sur des
    # LineString simples.
    routes = routes.explode(index_parts=False, ignore_index=True)
    routes = routes[routes.geometry.geom_type == "LineString"]
    routes = routes[shapely.get_num_coordinates(routes.geometry.values) >= 2]
    return routes[["classe", "geometry"]].reset_index(drop=True)


def zone_congestionnee() -> shapely.Geometry:
    """Union des communes de la ZMPP, en projection métrique."""
    communes = gpd.read_file(DATA_TRAITE / "communes.gpkg", layer="communes")
    zmpp = communes[communes["zmpp"]].to_crs(CRS_METRIQUE)
    exiger(len(zmpp) > 0, "aucune commune ZMPP identifiée, vérifier PCODES_ZMPP")
    return shapely.union_all(zmpp.geometry.values)


def construire(routes: gpd.GeoDataFrame, zmpp) -> dict:
    geoms = routes.geometry.values
    coords = shapely.get_coordinates(geoms)
    nb_points = shapely.get_num_coordinates(geoms)
    offsets = np.concatenate([[0], np.cumsum(nb_points)])

    # Toutes les positions sauf le dernier point de chaque polyligne ouvrent une
    # arête vers la position suivante.
    debut_arete = np.ones(len(coords), dtype=bool)
    debut_arete[offsets[1:] - 1] = False
    idx_u = np.nonzero(debut_arete)[0]
    idx_v = idx_u + 1

    ligne_par_point = np.repeat(np.arange(len(geoms)), nb_points)
    classe_par_arete = routes["classe"].to_numpy()[ligne_par_point[idx_u]]

    # Dédoublonnage des sommets au mètre : c'est ce qui soude le réseau.
    cle = np.round(coords).astype(np.int64)
    sommets, inverse = np.unique(cle, axis=0, return_inverse=True)
    inverse = inverse.ravel()
    u = inverse[idx_u]
    v = inverse[idx_v]

    longueurs = np.hypot(
        coords[idx_v, 0] - coords[idx_u, 0], coords[idx_v, 1] - coords[idx_u, 1]
    )

    vitesses = np.array([VITESSES_KMH[c] for c in classe_par_arete], dtype="float64")

    # Congestion urbaine : appliquée si le milieu de l'arête tombe dans la ZMPP.
    mx = (coords[idx_u, 0] + coords[idx_v, 0]) / 2
    my = (coords[idx_u, 1] + coords[idx_v, 1]) / 2
    dans_zmpp = shapely.contains_xy(zmpp, mx, my)
    vitesses = np.where(dans_zmpp, vitesses * FACTEUR_CONGESTION_ZMPP, vitesses)
    log(f"arêtes en zone congestionnée : {int(dans_zmpp.sum())} sur {len(u)}")

    # Temps de parcours en minutes.
    temps = longueurs / (vitesses * 1000.0 / 60.0)

    # Arêtes dégénérées (deux sommets confondus après arrondi) : écartées.
    valide = (u != v) & (longueurs > 0)
    log(f"arêtes dégénérées écartées : {int((~valide).sum())}")

    return {
        "sommets_x": sommets[:, 0].astype("float64"),
        "sommets_y": sommets[:, 1].astype("float64"),
        "u": u[valide].astype("int32"),
        "v": v[valide].astype("int32"),
        "temps_min": temps[valide].astype("float32"),
        "longueur_m": longueurs[valide].astype("float32"),
        "classe": classe_par_arete[valide].astype("U20"),
        "dans_zmpp": dans_zmpp[valide],
        "ux": coords[idx_u][valide, 0].astype("float64"),
        "uy": coords[idx_u][valide, 1].astype("float64"),
        "vx": coords[idx_v][valide, 0].astype("float64"),
        "vy": coords[idx_v][valide, 1].astype("float64"),
    }


def main() -> None:
    with etape("lecture du réseau routier"):
        routes = charger_routes()

    with etape("délimitation de la zone congestionnée"):
        zmpp = zone_congestionnee()

    with etape("construction du graphe"):
        graphe = construire(routes, zmpp)

    n_sommets = len(graphe["sommets_x"])
    n_aretes = len(graphe["u"])
    km = graphe["longueur_m"].sum() / 1000
    log(f"graphe : {n_sommets:,} sommets, {n_aretes:,} arêtes, {km:,.0f} km".replace(",", " "))
    exiger(n_aretes > 10_000, "graphe anormalement petit, vérifier le filtrage des classes")

    with etape("écriture"):
        np.savez_compressed(DATA_TRAITE / "graphe.npz", **graphe)

    log("étape 2 terminée")


if __name__ == "__main__":
    main()
