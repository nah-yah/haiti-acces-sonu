"""
Étape 4 : criticité des tronçons et scénarios de crise.

La criticité s'établit en deux temps : présélection par la charge, puis mesure
directe du dommage, l'accessibilité du pays entier étant recalculée sans chaque
tronçon présélectionné. Les deux classements ne coïncident pas. Une artère
fréquentée d'un quartier maillé se contourne ; un tronçon modeste qui est le
seul franchissement d'une ravine coûte des heures.

Cinq scénarios, de deux natures différentes :

  A  points de contrôle diffus              choc sur le réseau
  B  encerclement de la ZMPP                choc sur le réseau
  C  A et B cumulés                         choc sur le réseau
  D  fermeture des hôpitaux métropolitains  choc sur l'offre
  E  C et D cumulés                         crise combinée

Distinguer choc de réseau et choc d'offre est le cœur de l'exercice : savoir
lequel pèse le plus décide de l'affectation des moyens.

MISE EN GARDE. Ces scénarios ne sont pas des observations. Le jeu ACLED de HDX
est agrégé au mois et à la commune, sans coordonnée d'incident : il ne permet
pas de localiser un barrage réel. La géographie des coupures est un produit du
modèle, calculé par une règle explicite, et ne doit jamais être présentée comme
une carte des barrages existants.

Sorties :
  outputs/tables/04_*.csv
  data/processed/scenarios.parquet
  data/processed/points_controle.gpkg
"""

from __future__ import annotations

import sys
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import shapely
from shapely.geometry import LineString, Point

sys.path.insert(0, str(Path(__file__).resolve().parent))

from acces import (  # noqa: E402
    charger_graphe,
    flux_par_arete,
    indicateurs,
    mediane_ponderee,
    rattacher,
    temps_vers_offre,
)
from config import (  # noqa: E402
    CRS_METRIQUE,
    DATA_TRAITE,
    ESPACEMENT_MIN_CONTROLES_M,
    N_CANDIDATS_EVALUES,
    N_POINTS_CONTROLE,
    PART_EVENEMENTS_EXPOSEES,
    SEUILS_MINUTES,
    SEUIL_REFERENCE,
    TABLEAUX,
)
from utils import etape, exiger, log  # noqa: E402

# Axes structurants : un barrage se tient sur un axe qui porte du trafic, pas
# sur une desserte résidentielle en impasse.
CLASSES_AXES = {"motorway", "trunk", "primary", "secondary", "tertiary", "unclassified"}

# Paliers resserrés en bas d'échelle : le dommage se concentre sur les tout
# premiers tronçons, une grille à 0, 20, 40 masquerait la forme de la courbe.
PALIERS_CONTROLES = [0, 1, 2, 3, 4, 6, 8, 10, 15]


def communes_exposees(communes: gpd.GeoDataFrame) -> pd.Series:
    """Communes cumulant PART_EVENEMENTS_EXPOSEES des événements ACLED."""
    classement = communes.sort_values("evenements_acled", ascending=False)
    total = classement["evenements_acled"].sum()
    exiger(total > 0, "aucun événement ACLED, les scénarios n'ont pas de support")

    part_cumulee = classement["evenements_acled"].cumsum() / total
    retenues = classement[part_cumulee.shift(fill_value=0) < PART_EVENEMENTS_EXPOSEES]
    log(
        f"{len(retenues)} communes concentrent {PART_EVENEMENTS_EXPOSEES:.0%} "
        f"des {int(total)} événements de la fenêtre"
    )
    log(
        "  "
        + ", ".join(
            f"{r.commune} ({int(r.evenements_acled)})"
            for r in retenues.head(12).itertuples()
        )
    )
    return retenues["pcode"]


def ecarter_les_voisins(
    ordonnes: np.ndarray, mx: np.ndarray, my: np.ndarray, n: int, espacement: float
) -> np.ndarray:
    """
    Parcourt une liste déjà classée et n'en retient que des tronçons éloignés.

    Contrainte appliquée dès la présélection : les arêtes étant les segments
    entre points de forme, les cinquante tronçons les plus chargés du pays
    décrivent deux ou trois kilomètres du même axe. Sans espacement, on
    évaluerait cent cinquante fois le même barrage.
    """
    retenus: list[int] = []
    for idx in ordonnes:
        if len(retenus) >= n:
            break
        if retenus:
            d = np.hypot(mx[retenus] - mx[idx], my[retenus] - my[idx])
            if d.min() < espacement:
                continue
        retenus.append(int(idx))
    return np.array(retenus, dtype="int64")


def evaluer_candidats(
    graphe, sommets_sonuc, sommets_demande, minutes_acces, poids,
    candidats: np.ndarray, reference: np.ndarray,
) -> pd.DataFrame:
    """
    Mesure le dommage réel de la coupure de chaque tronçon candidat.

    Les minutes perdues pondérées quantifient l'allongement total des trajets ;
    la demande décrochée compte les femmes passant au-delà du seuil. La seconde
    est plus parlante mais sature : aucune coupure isolée ne fait basculer qui
    que ce soit au-delà de deux heures, d'où le seuil ramené à soixante minutes.
    """
    couvert_avant = reference <= SEUIL_REFERENCE
    ref_finie = np.isfinite(reference)
    lignes = []
    for rang, idx in enumerate(candidats, start=1):
        masque = np.zeros(len(graphe.u), dtype=bool)
        masque[idx] = True
        minutes, _, _ = temps_vers_offre(
            graphe, sommets_sonuc, sommets_demande, minutes_acces, aretes_coupees=masque
        )
        decroche = couvert_avant & (minutes > SEUIL_REFERENCE)
        comparable = ref_finie & np.isfinite(minutes)
        perdues = np.subtract(minutes, reference, out=np.zeros_like(reference), where=comparable)
        lignes.append({
            "arete": int(idx),
            "demande_decrochee": float(poids[decroche].sum()),
            "minutes_perdues_ponderees": float((perdues * poids).sum()),
        })
        if rang % 25 == 0:
            log(f"   {rang} / {len(candidats)} tronçons évalués")
    return pd.DataFrame(lignes)


def selectionner_points_controle(dommages: pd.DataFrame, n: int) -> np.ndarray:
    """
    Retient les n tronçons dont la coupure coûte le plus.

    Classement sur les minutes perdues pondérées plutôt que sur la demande
    décrochée : celle-ci ne se déclenche qu'au franchissement du seuil et laisse
    d'innombrables ex aequo. Les candidats sont déjà espacés.
    """
    classement = dommages.sort_values(
        ["minutes_perdues_ponderees", "demande_decrochee"], ascending=False
    )
    return classement["arete"].to_numpy()[:n].astype("int64")


def aretes_franchissant(limite, graphe) -> np.ndarray:
    """Arêtes dont une extrémité est dans la zone et l'autre dehors."""
    u_dedans = shapely.contains_xy(limite, graphe.ux, graphe.uy)
    v_dedans = shapely.contains_xy(limite, graphe.vx, graphe.vy)
    return u_dedans != v_dedans


def main() -> None:
    with etape("chargement"):
        graphe = charger_graphe(DATA_TRAITE / "graphe.npz")
        ref = np.load(DATA_TRAITE / "reference.npz", allow_pickle=False)
        cellules = pd.read_parquet(DATA_TRAITE / "cellules_reference.parquet")
        communes = gpd.read_file(DATA_TRAITE / "communes.gpkg", layer="communes").to_crs(
            CRS_METRIQUE
        )
        structures = gpd.read_file(DATA_TRAITE / "structures.gpkg", layer="structures").to_crs(
            CRS_METRIQUE
        )

        sommets_demande = ref["sommets_demande"]
        minutes_acces = ref["minutes_acces"]
        sommets_sonuc = ref["sommets_sonuc"]
        predecesseurs = ref["predecesseurs"]
        poids = cellules["demande_obstetricale"].to_numpy()
        reference_minutes = cellules["minutes_sonuc"].to_numpy()

    with etape("charge portée par chaque tronçon"):
        charge = flux_par_arete(graphe, sommets_demande, poids, predecesseurs)
        log(
            f"tronçons portant une charge non nulle : "
            f"{int((charge > 0).sum()):,} sur {len(charge):,}".replace(",", " ")
        )

    mx = (graphe.ux + graphe.vx) / 2
    my = (graphe.uy + graphe.vy) / 2

    with etape("rattachement administratif des tronçons chargés"):
        top = np.argsort(-charge)[:30_000]
        pts = gpd.GeoDataFrame(
            {"arete": top},
            geometry=[Point(x, y) for x, y in zip(mx[top], my[top])],
            crs=CRS_METRIQUE,
        )
        pts = gpd.sjoin(
            pts, communes[["pcode", "commune", "geometry"]], how="left", predicate="within"
        )
        pcode_par_arete = pd.Series(index=range(len(charge)), dtype="object")
        pcode_par_arete.loc[pts["arete"].to_numpy()] = pts["pcode"].to_numpy()

    with etape("identification des communes exposées"):
        exposees = set(communes_exposees(communes))
        eligible = (
            pcode_par_arete.isin(exposees).to_numpy()
            & np.isin(graphe.classe, list(CLASSES_AXES))
            & (charge > 0)
        )
        log(f"tronçons candidats après filtrage : {int(eligible.sum())}")

    with etape(f"évaluation directe de {N_CANDIDATS_EVALUES} tronçons présélectionnés"):
        pool = np.nonzero(eligible)[0]
        pool = pool[np.argsort(-charge[pool])]
        candidats = ecarter_les_voisins(
            pool, mx, my, N_CANDIDATS_EVALUES, ESPACEMENT_MIN_CONTROLES_M
        )
        log(
            f"{len(candidats)} candidats retenus, espacés d'au moins "
            f"{ESPACEMENT_MIN_CONTROLES_M / 1000:.0f} km, sur un vivier de {len(pool)} tronçons"
        )
        dommages = evaluer_candidats(
            graphe, sommets_sonuc, sommets_demande, minutes_acces, poids,
            candidats, reference_minutes,
        )
        dommages["charge"] = charge[dommages["arete"].to_numpy()]
        dommages["classe"] = graphe.classe[dommages["arete"].to_numpy()]
        dommages["commune"] = pcode_par_arete.loc[dommages["arete"]].to_numpy()
        dommages = dommages.sort_values("minutes_perdues_ponderees", ascending=False)
        dommages.to_csv(TABLEAUX / "04_criticite_troncons.csv", index=False)

        # L'écart entre les deux classements est un résultat en soi.
        rang_charge = dommages["charge"].rank(ascending=False)
        rang_dommage = dommages["minutes_perdues_ponderees"].rank(ascending=False)
        correlation = rang_charge.corr(rang_dommage, method="spearman")
        log(
            f"corrélation de rang entre charge et dommage mesuré : {correlation:.2f}. "
            "Une valeur faible confirme que la fréquentation d'un tronçon ne dit "
            "pas ce que sa coupure coûte."
        )
        log("\nDix tronçons les plus critiques :")
        log("\n" + dommages.head(10).to_string(index=False, float_format=lambda v: f"{v:,.0f}"))

    with etape("construction des scénarios"):
        idx_a = selectionner_points_controle(dommages, N_POINTS_CONTROLE)
        coupees_a = np.zeros(len(charge), dtype=bool)
        coupees_a[idx_a] = True
        log(f"scénario A : {len(idx_a)} points de contrôle")

        # L'encerclement coupe toutes les classes, pistes comprises : un blocage
        # qui laisserait les rues de quartier ouvertes n'encerclerait rien.
        zmpp = shapely.union_all(communes.loc[communes["zmpp"]].geometry.values)
        coupees_b = aretes_franchissant(zmpp, graphe)
        log(
            f"scénario B : {int(coupees_b.sum())} tronçons franchissant la limite "
            f"de la ZMPP, toutes classes confondues"
        )

        coupees_c = coupees_a | coupees_b

        # Choc d'offre : le réseau reste intact, seuls les hôpitaux de l'aire
        # métropolitaine cessent de fonctionner.
        sonuc = structures[structures["niveau"] == "SONUC"].copy()
        sonuc["dans_zmpp"] = shapely.contains_xy(
            zmpp, sonuc.geometry.x.to_numpy(), sonuc.geometry.y.to_numpy()
        )
        hors_zmpp = sonuc[~sonuc["dans_zmpp"]]
        sommets_hors_zmpp, _ = rattacher(
            graphe, hors_zmpp.geometry.x.to_numpy(), hors_zmpp.geometry.y.to_numpy()
        )
        log(
            f"scénario D : {int(sonuc['dans_zmpp'].sum())} hôpitaux de la ZMPP fermés, "
            f"{len(hors_zmpp)} restants dans le pays"
        )

    with etape("évaluation des scénarios"):
        # Le nombre d'hôpitaux ouverts est porté explicitement : plusieurs
        # structures se rattachent parfois au même sommet du graphe, et compter
        # les sommets de l'offre en sous-estimerait le total.
        scenarios = [
            ("Référence, réseau et offre intacts", None, sommets_sonuc, len(sonuc)),
            (f"A. {len(idx_a)} points de contrôle", coupees_a, sommets_sonuc, len(sonuc)),
            ("B. Encerclement de la ZMPP", coupees_b, sommets_sonuc, len(sonuc)),
            ("C. A et B cumulés", coupees_c, sommets_sonuc, len(sonuc)),
            ("D. Fermeture des hôpitaux de la ZMPP", None, sommets_hors_zmpp, len(hors_zmpp)),
            ("E. C et D cumulés", coupees_c, sommets_hors_zmpp, len(hors_zmpp)),
        ]

        resultats, minutes_par_scenario = [], {}
        for libelle, coupees, offre, hopitaux_ouverts in scenarios:
            minutes, _, _ = temps_vers_offre(
                graphe, offre, sommets_demande, minutes_acces, aretes_coupees=coupees
            )
            ind = indicateurs(minutes, poids, SEUILS_MINUTES)
            ind["scenario"] = libelle
            ind["troncons_coupes"] = int(coupees.sum()) if coupees is not None else 0
            ind["hopitaux_ouverts"] = hopitaux_ouverts
            resultats.append(ind)
            minutes_par_scenario[libelle] = minutes
            log(
                f"{libelle} : {ind[f'part_{SEUIL_REFERENCE}min']:.1%} de la demande "
                f"à moins de {SEUIL_REFERENCE} min, médiane {ind['mediane_min']:.0f} min, "
                f"{ind['part_non_atteignable']:.1%} sans accès routier à un hôpital"
            )

        tableau = pd.DataFrame(resultats).set_index("scenario")
        base = tableau.iloc[0][f"part_{SEUIL_REFERENCE}min"]
        tableau["ecart_points_pct"] = (tableau[f"part_{SEUIL_REFERENCE}min"] - base) * 100
        tableau["demande_decrochee"] = (
            (base - tableau[f"part_{SEUIL_REFERENCE}min"]) * tableau["demande_totale"]
        ).round(0)
        tableau.to_csv(TABLEAUX / "04_synthese_scenarios.csv")

    with etape("courbe de dégradation"):
        courbe = []
        paliers = [n for n in PALIERS_CONTROLES if n <= len(dommages)]
        for n in paliers:
            if n == 0:
                coupees = None
            else:
                idx = selectionner_points_controle(dommages, n)
                coupees = np.zeros(len(charge), dtype=bool)
                coupees[idx] = True
            minutes, _, _ = temps_vers_offre(
                graphe, sommets_sonuc, sommets_demande, minutes_acces, aretes_coupees=coupees
            )
            ind = indicateurs(minutes, poids, SEUILS_MINUTES)
            ind["n_points_controle"] = n
            courbe.append(ind)
            log(f"  {n:>3} points : {ind[f'part_{SEUIL_REFERENCE}min']:.1%} couverts")
        pd.DataFrame(courbe).to_csv(TABLEAUX / "04_courbe_degradation.csv", index=False)

    with etape("impact par commune et écriture"):
        cles = {}
        for i, (libelle, *_) in enumerate(scenarios):
            cle = "ref" if i == 0 else libelle.split(".")[0].strip().lower()
            cles[libelle] = f"min_{cle}"
            cellules[f"min_{cle}"] = minutes_par_scenario[libelle]

        ref_min = minutes_par_scenario[scenarios[0][0]]
        pire = minutes_par_scenario[scenarios[-1][0]]
        cellules["decrochee"] = (ref_min <= SEUIL_REFERENCE) & (pire > SEUIL_REFERENCE)
        # inf moins inf vaut NaN et déclenche un avertissement : les cellules
        # inatteignables dans les deux états sont neutralisées.
        comparable = np.isfinite(pire) & np.isfinite(ref_min)
        cellules["minutes_perdues"] = np.subtract(
            pire, ref_min, out=np.full(len(pire), np.nan), where=comparable
        )

        impact = cellules.groupby(
            ["departement", "pcode", "commune"], as_index=False
        ).apply(
            lambda g: pd.Series({
                "demande": g["demande_obstetricale"].sum(),
                "demande_decrochee": g.loc[g["decrochee"], "demande_obstetricale"].sum(),
                "minutes_perdues_medianes": mediane_ponderee(
                    g["minutes_perdues"].to_numpy(), g["demande_obstetricale"].to_numpy()
                ),
            }),
            include_groups=False,
        )
        impact["part_decrochee"] = impact["demande_decrochee"] / impact["demande"]
        impact = impact.sort_values("demande_decrochee", ascending=False)
        impact.to_csv(TABLEAUX / "04_impact_par_commune.csv", index=False)
        log("\nCommunes les plus touchées par le scénario combiné :")
        log("\n" + impact.head(12).to_string(index=False, float_format=lambda v: f"{v:,.1f}"))

        cellules.to_parquet(DATA_TRAITE / "scenarios.parquet", index=False)

        controles = gpd.GeoDataFrame(
            dommages[dommages["arete"].isin(idx_a)].copy(),
            geometry=[
                LineString([(graphe.ux[i], graphe.uy[i]), (graphe.vx[i], graphe.vy[i])])
                for i in dommages.loc[dommages["arete"].isin(idx_a), "arete"]
            ],
            crs=CRS_METRIQUE,
        )
        controles.to_file(DATA_TRAITE / "points_controle.gpkg", layer="controles", driver="GPKG")

        critiques = np.argsort(-charge)[:2000]
        gpd.GeoDataFrame(
            {"charge_demande": charge[critiques], "classe": graphe.classe[critiques]},
            geometry=[
                LineString([(graphe.ux[i], graphe.uy[i]), (graphe.vx[i], graphe.vy[i])])
                for i in critiques
            ],
            crs=CRS_METRIQUE,
        ).to_file(DATA_TRAITE / "troncons_critiques.gpkg", layer="critiques", driver="GPKG")

    log("étape 4 terminée")


if __name__ == "__main__":
    main()
