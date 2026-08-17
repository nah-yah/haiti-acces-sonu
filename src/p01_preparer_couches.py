"""
Étape 1 : préparation des couches d'entrée.

Produit dans data/processed :

  communes.gpkg     140 communes, population 2024, intensité ACLED, ZMPP
  structures.gpkg   structures de santé qualifiées SONUB / SONUC
  cellules.parquet  demande obstétricale maillée à 1 km, rattachée à sa commune
  offre_demande.csv récapitulatif de contrôle

Point délicat : le passage de WorldPop 2020 aux effectifs communaux 2024. Les
cellules sont redressées commune par commune pour que leur somme reproduise le
total OCHA COD-PS 2024. WorldPop donne la forme spatiale de la distribution, le
recensement projeté en donne le niveau.
"""

from __future__ import annotations

import sys
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
from shapely.geometry import Point

sys.path.insert(0, str(Path(__file__).resolve().parent))

from config import (  # noqa: E402
    CRS_METRIQUE,
    CRS_SOURCE,
    DATA_BRUT,
    DATA_TRAITE,
    FACTEUR_AGREGATION,
    FENETRE_ACLED_MOIS,
    PCODES_ZMPP,
    POP_MIN_CELLULE,
    TABLEAUX,
    TAG_SONUC,
    TAGS_HORS_PERIMETRE,
    TAGS_SONUB,
)
from utils import etape, exiger, log, trouver_colonne  # noqa: E402

TRANCHES_FEMMES_15_49 = [
    "F_15_19", "F_20_24", "F_25_29", "F_30_34", "F_35_39", "F_40_44", "F_45_49",
]


def lire_csv_tolerant(chemin: Path) -> pd.DataFrame:
    """Les exports OCHA alternent entre UTF-8 et CP1252 selon le millésime."""
    for encodage in ("utf-8", "cp1252", "latin-1"):
        try:
            return pd.read_csv(chemin, encoding=encodage)
        except UnicodeDecodeError:
            continue
    raise UnicodeDecodeError(f"encodage non reconnu pour {chemin}")


# --------------------------------------------------------------------------
# Communes
# --------------------------------------------------------------------------

def charger_communes() -> gpd.GeoDataFrame:
    communes = gpd.read_file(DATA_BRUT / "hti_admin_boundaries" / "hti_admin2.shp")
    # Les millésimes COD-AB alternent entre `ADM2_FR` et `adm2_name`.
    col_pcode = trouver_colonne(communes.columns, "ADM2_PCODE")
    col_nom = trouver_colonne(communes.columns, "ADM2_FR", "ADM2_EN", "ADM2_NAME")
    col_dept = trouver_colonne(communes.columns, "ADM1_FR", "ADM1_EN", "ADM1_NAME")

    communes = communes.rename(
        columns={col_pcode: "pcode", col_nom: "commune", col_dept: "departement"}
    )[["pcode", "commune", "departement", "geometry"]]

    if communes.crs is None:
        communes = communes.set_crs(CRS_SOURCE)
    communes = communes.to_crs(CRS_SOURCE)
    communes["zmpp"] = communes["pcode"].isin(PCODES_ZMPP)

    exiger(len(communes) == 140, f"140 communes attendues, {len(communes)} lues")
    exiger(communes["pcode"].is_unique, "codes ADM2 dupliqués")
    return communes


def ajouter_population(communes: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    pop = lire_csv_tolerant(DATA_BRUT / "hti_admpop_adm2_2024.csv")
    col_pcode = trouver_colonne(pop.columns, "ADM2_PCODE")
    pop = pop.rename(columns={col_pcode: "pcode"})

    manquantes = [c for c in TRANCHES_FEMMES_15_49 if c not in pop.columns]
    exiger(not manquantes, f"tranches d'âge absentes du fichier population : {manquantes}")

    # Pas de colonne agrégée dans COD-PS : les sept tranches quinquennales sont
    # sommées, comme dans le projet SSR 2024.
    pop["femmes_15_49"] = pop[TRANCHES_FEMMES_15_49].sum(axis=1)
    pop = pop.rename(columns={"T_TL": "pop_totale"})[
        ["pcode", "pop_totale", "femmes_15_49"]
    ]

    communes = communes.merge(pop, on="pcode", how="left", validate="one_to_one")
    exiger(
        communes["pop_totale"].notna().all(),
        "des communes n'ont pas trouvé leur population dans le fichier COD-PS",
    )
    # Convertit une cellule de population totale en demande obstétricale.
    communes["part_femmes_15_49"] = communes["femmes_15_49"] / communes["pop_totale"]
    return communes


def ajouter_intensite_acled(communes: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """
    Intensité des violences contre les civils par commune, sur les
    FENETRE_ACLED_MOIS derniers mois du jeu ACLED.

    Le jeu HDX est agrégé au mois et à la commune, sans coordonnées d'événement :
    il mesure une intensité communale, il ne localise pas un incident.
    """
    chemin = DATA_BRUT / "acled_civilian_targeting_adm2.xlsx"
    if not chemin.exists():
        log("ACLED absent : intensité mise à zéro, les scénarios seront dégradés")
        communes["evenements_acled"] = 0.0
        return communes

    acled = pd.read_excel(chemin, sheet_name="Data")
    col_pcode = trouver_colonne(acled.columns, "Admin2 Pcode")
    col_mois = trouver_colonne(acled.columns, "Month")
    col_annee = trouver_colonne(acled.columns, "Year")
    col_evt = trouver_colonne(acled.columns, "Events")

    acled["date"] = pd.to_datetime(
        acled[col_annee].astype(str) + "-" + acled[col_mois].astype(str) + "-01",
        format="%Y-%B-%d",
        errors="coerce",
    )
    exiger(acled["date"].notna().any(), "dates ACLED illisibles")

    fin = acled["date"].max()
    debut = fin - pd.DateOffset(months=FENETRE_ACLED_MOIS - 1)
    fenetre = acled[acled["date"].between(debut, fin)]
    log(
        f"fenêtre ACLED : {debut:%Y-%m} à {fin:%Y-%m}, "
        f"{int(fenetre[col_evt].sum()):,} événements".replace(",", " ")
    )

    intensite = (
        fenetre.groupby(col_pcode, as_index=False)[col_evt]
        .sum()
        .rename(columns={col_pcode: "pcode", col_evt: "evenements_acled"})
    )
    communes = communes.merge(intensite, on="pcode", how="left")
    communes["evenements_acled"] = communes["evenements_acled"].fillna(0.0)
    return communes


# --------------------------------------------------------------------------
# Structures de santé
# --------------------------------------------------------------------------

def charger_structures(communes: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    points = gpd.read_file(DATA_BRUT / "hti_health_facilities" / "health_facilities_points.shp")
    if points.crs is None:
        points = points.set_crs(CRS_SOURCE)
    points = points.to_crs(CRS_SOURCE)

    col_amenity = trouver_colonne(points.columns, "amenity")
    col_healthcare = trouver_colonne(points.columns, "healthcare")
    try:
        col_nom = trouver_colonne(points.columns, "name")
    except KeyError:
        col_nom = None

    amenity = points[col_amenity].fillna("").astype(str).str.lower().str.strip()
    healthcare = points[col_healthcare].fillna("").astype(str).str.lower().str.strip()

    def classer(a: str, h: str) -> str:
        # Une pharmacie sort du périmètre même si elle porte par ailleurs une
        # étiquette de soins.
        if a in TAGS_HORS_PERIMETRE or h in TAGS_HORS_PERIMETRE:
            return "hors_perimetre"
        if h == TAG_SONUC:
            return "SONUC"
        if a == TAG_SONUC:
            return "HOPITAL_NC"
        if a in TAGS_SONUB or h in TAGS_SONUB:
            return "SONUB"
        return "hors_perimetre"

    points["niveau"] = [classer(a, h) for a, h in zip(amenity, healthcare)]
    points["nom"] = points[col_nom] if col_nom else ""

    structures = points[points["niveau"] != "hors_perimetre"].copy()
    structures = structures[["nom", "niveau", "geometry"]].reset_index(drop=True)

    # Rattachement administratif, pour les tableaux par département.
    structures = gpd.sjoin(
        structures, communes[["pcode", "commune", "departement", "geometry"]],
        how="left", predicate="within",
    ).drop(columns=["index_right"])

    repartition = structures["niveau"].value_counts()
    log(f"structures retenues : {len(structures)} sur {len(points)} points de santé")
    log("\n" + repartition.to_string())
    log(
        "  SONUC       étiquettes amenity et healthcare concordantes\n"
        "  HOPITAL_NC  amenity=hospital non confirmé, statut incertain\n"
        "  SONUB       première ligne, sans capacité chirurgicale présumée"
    )
    exiger(
        (structures["niveau"] == "SONUC").sum() > 20,
        "trop peu de SONUC identifiés, vérifier les tags OSM",
    )
    return structures


# --------------------------------------------------------------------------
# Demande maillée
# --------------------------------------------------------------------------

def construire_cellules(communes: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Agrège WorldPop 100 m en cellules d'environ 1 km, puis les redresse."""
    chemin = DATA_BRUT / "hti_ppp_2020_UNadj_constrained.tif"
    exiger(chemin.exists(), f"raster de population absent : {chemin}")

    with rasterio.open(chemin) as src:
        grille = src.read(1).astype("float64")
        nodata = src.nodata
        transform = src.transform
        crs_raster = src.crs

    grille = np.where(
        np.isnan(grille) | (grille < 0) | ((nodata is not None) & (grille == nodata)),
        0.0,
        grille,
    )

    f = FACTEUR_AGREGATION
    h, w = grille.shape
    H, W = -(-h // f) * f, -(-w // f) * f
    rembourree = np.zeros((H, W), dtype="float64")
    rembourree[:h, :w] = grille
    agregee = rembourree.reshape(H // f, f, W // f, f).sum(axis=(1, 3))

    lignes, colonnes = np.nonzero(agregee >= POP_MIN_CELLULE)
    valeurs = agregee[lignes, colonnes]

    # Centre de chaque cellule agrégée, référentiel du raster source.
    x = transform.c + (colonnes + 0.5) * f * transform.a
    y = transform.f + (lignes + 0.5) * f * transform.e

    cellules = gpd.GeoDataFrame(
        {"pop_2020": valeurs},
        geometry=[Point(xi, yi) for xi, yi in zip(x, y)],
        crs=crs_raster,
    ).to_crs(CRS_SOURCE)

    log(
        f"cellules peuplées : {len(cellules)} "
        f"pour {agregee.sum() / 1e6:.2f} millions d'habitants (WorldPop 2020)"
    )
    return cellules


def rattacher_et_redresser(
    cellules: gpd.GeoDataFrame, communes: gpd.GeoDataFrame
) -> gpd.GeoDataFrame:
    """Affecte chaque cellule à une commune puis cale les totaux sur COD-PS 2024."""
    colonnes_com = ["pcode", "commune", "departement", "zmpp", "part_femmes_15_49", "geometry"]

    dedans = gpd.sjoin(
        cellules, communes[colonnes_com], how="left", predicate="within"
    ).drop(columns=["index_right"])

    # Les cellules du littoral tombent parfois hors polygone, le trait de côte
    # étant généralisé. Rattachées au plus proche plutôt que perdues.
    orphelines = dedans["pcode"].isna()
    if orphelines.any():
        log(f"rattachement au plus proche pour {int(orphelines.sum())} cellules côtières")
        reprises = gpd.sjoin_nearest(
            cellules.loc[orphelines].to_crs(CRS_METRIQUE),
            communes[colonnes_com].to_crs(CRS_METRIQUE),
            how="left",
        ).drop(columns=["index_right"])
        reprises = reprises.to_crs(CRS_SOURCE)
        for col in ["pcode", "commune", "departement", "zmpp", "part_femmes_15_49"]:
            dedans.loc[orphelines, col] = reprises[col].to_numpy()

    dedans = dedans[dedans["pcode"].notna()].copy()

    # Redressement : la somme des cellules d'une commune doit valoir son
    # effectif COD-PS 2024.
    totaux_2020 = dedans.groupby("pcode")["pop_2020"].transform("sum")
    cible = dedans["pcode"].map(communes.set_index("pcode")["pop_totale"])
    facteur = np.where(totaux_2020 > 0, cible / totaux_2020, 0.0)
    dedans["pop"] = dedans["pop_2020"] * facteur
    dedans["facteur_redressement"] = facteur

    ecarts = (
        dedans.groupby("pcode")["facteur_redressement"].first().sort_values(ascending=False)
    )
    log(
        f"facteur de redressement : médiane {ecarts.median():.2f}, "
        f"étendue {ecarts.min():.2f} à {ecarts.max():.2f}"
    )

    dedans["demande_obstetricale"] = dedans["pop"] * dedans["part_femmes_15_49"]

    total = dedans["pop"].sum()
    attendu = communes["pop_totale"].sum()
    exiger(
        abs(total - attendu) / attendu < 0.01,
        f"le redressement ne boucle pas : {total:,.0f} contre {attendu:,.0f}",
    )
    log(f"population maillée après redressement : {total / 1e6:.2f} millions")
    return dedans.reset_index(drop=True)


# --------------------------------------------------------------------------

def main() -> None:
    with etape("chargement des communes"):
        communes = charger_communes()
        communes = ajouter_population(communes)
        communes = ajouter_intensite_acled(communes)

    with etape("chargement des structures de santé"):
        structures = charger_structures(communes)

    with etape("construction de la demande maillée"):
        cellules = construire_cellules(communes)
        cellules = rattacher_et_redresser(cellules, communes)

    with etape("écriture"):
        communes.to_file(DATA_TRAITE / "communes.gpkg", layer="communes", driver="GPKG")
        structures.to_file(DATA_TRAITE / "structures.gpkg", layer="structures", driver="GPKG")

        plat = cellules.copy()
        plat["x"] = plat.geometry.x
        plat["y"] = plat.geometry.y
        plat.drop(columns="geometry").to_parquet(
            DATA_TRAITE / "cellules.parquet", index=False
        )

        recap = (
            cellules.groupby(["departement", "pcode", "commune"], as_index=False)
            .agg(
                cellules=("pop", "size"),
                population=("pop", "sum"),
                demande_obstetricale=("demande_obstetricale", "sum"),
            )
            .merge(
                structures.groupby("pcode")["niveau"]
                .value_counts()
                .unstack(fill_value=0)
                .reset_index(),
                on="pcode",
                how="left",
            )
            .fillna({"SONUB": 0, "SONUC": 0})
        )
        recap.to_csv(TABLEAUX / "01_offre_demande_par_commune.csv", index=False)

    log("étape 1 terminée")


if __name__ == "__main__":
    main()
