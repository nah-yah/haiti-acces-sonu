"""
Étape 3 : accessibilité de référence, réseau intact.

Trois définitions de l'offre sont mesurées séparément, parce que la donnée ne
permet pas d'en trancher une seule :

  SONUC          198 points dont les étiquettes `amenity` et `healthcare`
                 concordent sur « hôpital ». Définition retenue pour la suite
                 de l'analyse : c'est la borne prudente.
  SONUC élargi   les 198 précédents plus 986 points portant `amenity=hospital`
                 sans confirmation. Borne haute, presque certainement
                 optimiste.
  Toute offre    l'ensemble des structures de soins, cliniques comprises.
                 Décrit l'accès à la première ligne, pas à la césarienne.

L'écart entre les deux premières bornes est la mesure directe de ce que
l'incertitude sur les étiquettes OSM coûte à l'analyse. Le publier vaut mieux
que de choisir en silence.

Une hémorragie du post-partum ou une dystocie se traite au bloc, pas au
dispensaire : c'est la première ligne du tableau qui répond à la question du
commanditaire.

Sorties :
  data/processed/cellules_reference.parquet
  data/processed/reference.npz            distances et prédécesseurs réutilisés par l'étape 4
  outputs/tables/03_*.csv
"""

from __future__ import annotations

import sys
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))

from acces import (  # noqa: E402
    charger_graphe,
    composantes,
    indicateurs,
    mediane_ponderee,
    rattacher,
    temps_vers_offre,
)
from config import (  # noqa: E402
    CRS_METRIQUE,
    DATA_TRAITE,
    SEUILS_MINUTES,
    TABLEAUX,
)
from utils import etape, exiger, log  # noqa: E402


def charger_demande() -> pd.DataFrame:
    cellules = pd.read_parquet(DATA_TRAITE / "cellules.parquet")
    points = gpd.GeoSeries(
        gpd.points_from_xy(cellules["x"], cellules["y"]), crs="EPSG:4326"
    ).to_crs(CRS_METRIQUE)
    cellules["xm"] = points.x.to_numpy()
    cellules["ym"] = points.y.to_numpy()
    return cellules


def charger_offre() -> gpd.GeoDataFrame:
    structures = gpd.read_file(DATA_TRAITE / "structures.gpkg", layer="structures")
    return structures.to_crs(CRS_METRIQUE)


def main() -> None:
    with etape("chargement du graphe et des couches"):
        graphe = charger_graphe(DATA_TRAITE / "graphe.npz")
        cellules = charger_demande()
        structures = charger_offre()
        log(f"{len(cellules)} cellules de demande, {len(structures)} structures")

    with etape("rattachement au réseau"):
        sommets_demande, minutes_acces = rattacher(
            graphe, cellules["xm"].to_numpy(), cellules["ym"].to_numpy()
        )
        hors_reseau = ~np.isfinite(minutes_acces)
        part_hors = cellules.loc[hors_reseau, "demande_obstetricale"].sum() / cellules[
            "demande_obstetricale"
        ].sum()
        log(
            f"cellules à plus de 10 km de toute route carrossable : "
            f"{int(hors_reseau.sum())} ({part_hors:.1%} de la demande)"
        )

        definitions = {
            "SONUC": ["SONUC"],
            "SONUC élargi": ["SONUC", "HOPITAL_NC"],
            "Toute offre de soins": ["SONUC", "HOPITAL_NC", "SONUB"],
        }
        sommets_offre = {}
        for libelle, niveaux in definitions.items():
            sous = structures[structures["niveau"].isin(niveaux)]
            sommets_offre[libelle], _ = rattacher(
                graphe, sous.geometry.x.to_numpy(), sous.geometry.y.to_numpy()
            )
            log(f"  {libelle} : {len(sous)} structures")
        sommets_sonuc = sommets_offre["SONUC"]
        exiger(len(sommets_sonuc) > 0, "aucune structure SONUC identifiée")

    with etape("diagnostic de connexité du réseau"):
        etiquettes = composantes(graphe)
        taille = pd.Series(etiquettes).value_counts()
        principale = taille.index[0]
        part_principale = taille.iloc[0] / len(etiquettes)
        log(
            f"{len(taille)} composantes ; la principale porte {part_principale:.1%} "
            f"des sommets. Les composantes secondaires correspondent aux îles "
            f"(Gonâve, Tortue, Île-à-Vache) et aux tronçons isolés d'OSM."
        )
        cellules["composante"] = etiquettes[sommets_demande]
        cellules["reseau_principal"] = cellules["composante"] == principale

    colonnes_temps = {
        "SONUC": "minutes_sonuc",
        "SONUC élargi": "minutes_sonuc_elargi",
        "Toute offre de soins": "minutes_sonu",
    }

    with etape("Dijkstra multi-sources, une passe par définition de l'offre"):
        predecesseurs = sources = None
        for libelle, colonne in colonnes_temps.items():
            # Les itinéraires ne sont conservés que pour la définition retenue :
            # ce sont eux qui serviront à mesurer la criticité des tronçons.
            garder_chemins = libelle == "SONUC"
            minutes, pred, src = temps_vers_offre(
                graphe, sommets_offre[libelle], sommets_demande, minutes_acces,
                avec_chemins=garder_chemins,
            )
            cellules[colonne] = minutes
            if garder_chemins:
                predecesseurs, sources = pred, src
            log(f"  {libelle} : calcul terminé")

    with etape("indicateurs"):
        poids = cellules["demande_obstetricale"].to_numpy()
        lignes = []
        for libelle, colonne in colonnes_temps.items():
            ind = indicateurs(cellules[colonne].to_numpy(), poids, SEUILS_MINUTES)
            ind["offre"] = libelle
            lignes.append(ind)
        national = pd.DataFrame(lignes).set_index("offre")
        log("\n" + national.to_string(float_format=lambda v: f"{v:,.3f}"))
        national.to_csv(TABLEAUX / "03_accessibilite_nationale.csv")

        par_commune = (
            cellules.groupby(["departement", "pcode", "commune"], as_index=False)
            .apply(
                lambda g: pd.Series(
                    {
                        "demande": g["demande_obstetricale"].sum(),
                        "population": g["pop"].sum(),
                        "mediane_sonuc_min": mediane_ponderee(
                            g["minutes_sonuc"].to_numpy(),
                            g["demande_obstetricale"].to_numpy(),
                        ),
                        "part_60min_sonuc": g.loc[
                            g["minutes_sonuc"] <= 60, "demande_obstetricale"
                        ].sum()
                        / g["demande_obstetricale"].sum(),
                        "part_120min_sonuc": g.loc[
                            g["minutes_sonuc"] <= 120, "demande_obstetricale"
                        ].sum()
                        / g["demande_obstetricale"].sum(),
                        "part_60min_sonuc_elargi": g.loc[
                            g["minutes_sonuc_elargi"] <= 60, "demande_obstetricale"
                        ].sum()
                        / g["demande_obstetricale"].sum(),
                        "part_60min_sonu": g.loc[
                            g["minutes_sonu"] <= 60, "demande_obstetricale"
                        ].sum()
                        / g["demande_obstetricale"].sum(),
                    }
                ),
                include_groups=False,
            )
        )
        par_commune = par_commune.sort_values("part_60min_sonuc")
        par_commune.to_csv(TABLEAUX / "03_accessibilite_par_commune.csv", index=False)
        log("\nDix communes les moins bien desservies (part de la demande à 60 min d'un SONUC) :")
        log("\n" + par_commune.head(10).to_string(index=False, float_format=lambda v: f"{v:,.2f}"))

    with etape("écriture"):
        cellules.to_parquet(DATA_TRAITE / "cellules_reference.parquet", index=False)
        np.savez_compressed(
            DATA_TRAITE / "reference.npz",
            sommets_demande=sommets_demande,
            minutes_acces=minutes_acces,
            sommets_sonuc=sommets_sonuc,
            predecesseurs=predecesseurs,
            sources=sources,
        )

    log("étape 3 terminée")


if __name__ == "__main__":
    main()
