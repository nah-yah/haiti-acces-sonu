"""
Étape 5 : cartes et graphiques.

Sept sorties dans outputs/figures, plus une carte interactive.
Chaque figure répond à une question, et une seule.
"""

from __future__ import annotations

import sys
from pathlib import Path

import geopandas as gpd
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.colors import BoundaryNorm
from matplotlib.lines import Line2D
from matplotlib.patches import Patch

sys.path.insert(0, str(Path(__file__).resolve().parent))

import style  # noqa: E402
from config import (  # noqa: E402
    CRS_METRIQUE,
    DATA_TRAITE,
    DPI_FIGURES,
    FIGURES,
    SEUILS_MINUTES,
    SEUIL_REFERENCE,
    TABLEAUX,
)
from utils import etape, log  # noqa: E402

SOURCE_COMMUNE = (
    "Sources : OCHA COD-AB et COD-PS 2024, WorldPop 2020, OpenStreetMap via HOT, ACLED. "
    "Analyse : Santé Commune Initiative (cas d'école)."
)


def charger():
    cellules = pd.read_parquet(DATA_TRAITE / "scenarios.parquet")
    communes = gpd.read_file(DATA_TRAITE / "communes.gpkg", layer="communes").to_crs(CRS_METRIQUE)
    structures = gpd.read_file(DATA_TRAITE / "structures.gpkg", layer="structures").to_crs(CRS_METRIQUE)
    controles = gpd.read_file(DATA_TRAITE / "points_controle.gpkg", layer="controles")
    critiques = gpd.read_file(DATA_TRAITE / "troncons_critiques.gpkg", layer="critiques")

    points = gpd.GeoSeries(
        gpd.points_from_xy(cellules["x"], cellules["y"]), crs="EPSG:4326"
    ).to_crs(CRS_METRIQUE)
    cellules["xm"] = points.x.to_numpy()
    cellules["ym"] = points.y.to_numpy()
    return cellules, communes, structures, controles, critiques


def enregistrer(fig, nom: str) -> None:
    chemin = FIGURES / nom
    fig.savefig(chemin, dpi=DPI_FIGURES, bbox_inches="tight", facecolor=style.SURFACE)
    plt.close(fig)
    log(f"figure écrite : {chemin.name}")


# --------------------------------------------------------------------------

def fig_accessibilite(cellules, communes, structures) -> None:
    """Temps de trajet vers l'hôpital le plus proche, réseau intact."""
    fig, ax = plt.subplots(figsize=(11, 7))
    communes.plot(ax=ax, color=style.FOND_TERRE, edgecolor=style.LIGNE_BASE, linewidth=0.4)

    minutes = cellules["minutes_sonuc"].to_numpy()
    fini = np.isfinite(minutes)
    tri = np.argsort(minutes[fini])

    nuage = ax.scatter(
        cellules["xm"].to_numpy()[fini][tri],
        cellules["ym"].to_numpy()[fini][tri],
        c=np.clip(minutes[fini][tri], 0, 240),
        cmap=style.CMAP_TEMPS, s=2.2, marker="s", linewidths=0, vmin=0, vmax=240,
    )
    # Ces cellules ne sont pas hors du réseau routier : elles appartiennent à un
    # sous-réseau qui ne contient aucun hôpital. Îles et vallées isolées d'OSM.
    ax.scatter(
        cellules["xm"].to_numpy()[~fini], cellules["ym"].to_numpy()[~fini],
        color=style.STATUT_CRITIQUE, s=2.6, marker="x", linewidths=0.45,
        label="Aucun hôpital atteignable par la route",
    )
    sonuc = structures[structures["niveau"] == "SONUC"]
    ax.scatter(
        sonuc.geometry.x, sonuc.geometry.y, s=14, facecolor="none",
        edgecolor=style.ENCRE_PRINCIPALE, linewidths=0.7, label="Hôpital (SONUC)",
    )

    barre = fig.colorbar(nuage, ax=ax, fraction=0.03, pad=0.01)
    barre.set_label("Minutes jusqu'à l'hôpital le plus proche", color=style.ENCRE_SECONDAIRE)
    barre.outline.set_visible(False)
    barre.ax.tick_params(color=style.ENCRE_ATTENUEE, labelcolor=style.ENCRE_ATTENUEE)

    ax.legend(loc="lower left", labelcolor=style.ENCRE_SECONDAIRE)
    style.habiller_carte(
        ax,
        "Temps de trajet vers un hôpital, réseau routier intact",
        "Population maillée à 1 km, pondérée par la part des femmes de 15 à 49 ans. Haïti, 2024.",
        SOURCE_COMMUNE,
    )
    enregistrer(fig, "fig01_accessibilite_reference.png")


def fig_couverture_communes(communes) -> None:
    """Part de la demande obstétricale à moins de 120 minutes d'un hôpital."""
    table = pd.read_csv(TABLEAUX / "03_accessibilite_par_commune.csv")
    colonne = f"part_{SEUIL_REFERENCE}min_sonuc"
    carte = communes.merge(table[["pcode", colonne]], on="pcode", how="left")
    sans_couverture = int((carte[colonne] == 0).sum())

    # C'est le déficit qui est tracé, non la couverture. Une rampe séquentielle
    # va du clair au foncé quand la grandeur augmente ; cartographier la
    # couverture obligerait à inverser la rampe, et un lecteur pressé lirait
    # alors le foncé comme « beaucoup », c'est-à-dire l'inverse du message.
    carte["deficit"] = 1 - carte[colonne]

    fig, ax = plt.subplots(figsize=(11, 7))
    carte.plot(
        column="deficit", ax=ax, cmap=style.CMAP_TEMPS,
        edgecolor=style.LIGNE_BASE, linewidth=0.4, vmin=0, vmax=1,
        missing_kwds={"color": style.FOND_TERRE, "label": "Sans donnée"},
        legend=True,
        legend_kwds={
            "label": f"Part de la demande à plus de {SEUIL_REFERENCE} minutes",
            "fraction": 0.03, "pad": 0.01,
        },
    )
    style.habiller_carte(
        ax,
        f"Demande obstétricale hors de portée d'un hôpital en {SEUIL_REFERENCE} minutes",
        f"Plus la commune est foncée, plus la part de sa demande hors de portée est élevée. "
        f"{sans_couverture} communes sont intégralement hors de portée.",
        SOURCE_COMMUNE,
    )
    enregistrer(fig, "fig02_couverture_par_commune.png")


def fig_troncons_critiques(communes, critiques, controles) -> None:
    """Tronçons portant la plus forte charge de demande, et coupures simulées."""
    fig, ax = plt.subplots(figsize=(11, 7))
    communes.plot(ax=ax, color=style.FOND_TERRE, edgecolor=style.LIGNE_BASE, linewidth=0.4)

    charge = critiques["charge_demande"].to_numpy()
    epaisseur = 0.3 + 2.7 * (charge / charge.max()) ** 0.5
    critiques.plot(ax=ax, color=style.SERIE_1, linewidth=epaisseur, alpha=0.85)
    controles.plot(ax=ax, color=style.STATUT_CRITIQUE, linewidth=3.0)
    ax.scatter(
        controles.geometry.centroid.x, controles.geometry.centroid.y,
        s=40, facecolor="none", edgecolor=style.STATUT_CRITIQUE, linewidths=1.2,
    )

    ax.legend(
        handles=[
            Line2D([0], [0], color=style.SERIE_1, lw=2,
                   label="Tronçon critique (épaisseur : demande portée)"),
            Line2D([0], [0], color=style.STATUT_CRITIQUE, lw=3,
                   label="Point de contrôle simulé, scénario A"),
        ],
        loc="lower left", labelcolor=style.ENCRE_SECONDAIRE,
    )
    style.habiller_carte(
        ax,
        "Tronçons critiques et points de contrôle simulés",
        "La charge d'un tronçon est la demande obstétricale dont l'itinéraire le plus rapide l'emprunte. "
        "Les points de contrôle sont un produit du modèle, pas une observation de terrain.",
        SOURCE_COMMUNE,
    )
    enregistrer(fig, "fig03_troncons_critiques.png")


def fig_impact(cellules, communes) -> None:
    """Cellules qui basculent au-delà du seuil de référence dans le scénario cumulé."""
    fig, ax = plt.subplots(figsize=(11, 7))
    communes.plot(ax=ax, color=style.FOND_TERRE, edgecolor=style.LIGNE_BASE, linewidth=0.4)

    conserve = ~cellules["decrochee"].to_numpy()
    ax.scatter(
        cellules["xm"].to_numpy()[conserve], cellules["ym"].to_numpy()[conserve],
        color=style.LIGNE_BASE, s=1.4, marker="s", linewidths=0,
    )
    perdu = cellules["decrochee"].to_numpy()
    ax.scatter(
        cellules["xm"].to_numpy()[perdu], cellules["ym"].to_numpy()[perdu],
        color=style.STATUT_CRITIQUE, s=4.5, marker="s", linewidths=0,
    )

    demande_perdue = cellules.loc[perdu, "demande_obstetricale"].sum()
    ax.legend(
        handles=[
            Patch(facecolor=style.LIGNE_BASE, label="Accès conservé"),
            Patch(
                facecolor=style.STATUT_CRITIQUE,
                label=f"Accès perdu : {demande_perdue:,.0f} femmes de 15 à 49 ans".replace(",", " "),
            ),
        ],
        loc="lower left", labelcolor=style.ENCRE_SECONDAIRE,
    )
    style.habiller_carte(
        ax,
        f"Demande basculant au-delà de {SEUIL_REFERENCE} minutes, scénario combiné",
        "Scénario E : points de contrôle diffus, encerclement de l'aire métropolitaine et "
        "fermeture des hôpitaux qu'elle abrite. La perte suit le corridor de la RN1.",
        SOURCE_COMMUNE,
    )
    enregistrer(fig, "fig04_impact_scenario_cumule.png")


def fig_courbe_degradation() -> None:
    """Perte de couverture en fonction du nombre de points de contrôle."""
    courbe = pd.read_csv(TABLEAUX / "04_courbe_degradation.csv")

    # L'indicateur est exprimé en nombre de femmes plutôt qu'en pourcentage.
    # En pourcentage, l'écart tient dans moins d'un point, et un axe cadré sur
    # cette plage donnerait à une variation de 0,8 point l'allure d'un
    # effondrement. En effectifs, l'axe part de zéro et la lecture est honnête.
    base = courbe.loc[courbe["n_points_controle"] == 0, f"part_{SEUIL_REFERENCE}min"].iloc[0]
    total = courbe["demande_totale"].iloc[0]
    y = (base - courbe[f"part_{SEUIL_REFERENCE}min"]) * total

    fig, ax = plt.subplots(figsize=(8.5, 4.8))
    ax.grid(axis="y", zorder=0)
    ax.plot(courbe["n_points_controle"], y, color=style.SERIE_1, lw=2, zorder=3)
    ax.scatter(courbe["n_points_controle"], y, color=style.SERIE_1, s=36,
               zorder=4, edgecolor=style.SURFACE, linewidths=2)

    # Étiquetage sélectif : le premier point et le dernier suffisent à lire la
    # forme, un chiffre sur chaque marqueur n'ajouterait que de l'encre.
    for i in (1, len(courbe) - 1):
        ax.annotate(
            f"{y.iloc[i]:,.0f}".replace(",", " "),
            (courbe["n_points_controle"].iloc[i], y.iloc[i]),
            textcoords="offset points", xytext=(6, 8), ha="left",
            fontsize=9, color=style.ENCRE_PRINCIPALE, weight="semibold",
        )

    ax.set_ylim(bottom=0)
    ax.set_xlabel("Nombre de points de contrôle posés")
    ax.set_ylabel("Femmes basculant au-delà d'une heure")
    part_premier = y.iloc[1] / y.iloc[-1] if y.iloc[-1] else np.nan
    style.titrer(
        ax,
        f"Le premier barrage emporte {part_premier:.0%} du dommage total",
        "Les tronçons sont classés par dommage mesuré, du plus coûteux au moins coûteux. "
        "Au-delà du sixième, couper davantage ne change presque plus rien : la vulnérabilité "
        "du réseau tient à une poignée de segments.",
    )
    enregistrer(fig, "fig05_courbe_degradation.png")


def fig_synthese_scenarios() -> None:
    """Couverture par seuil et par scénario."""
    table = pd.read_csv(TABLEAUX / "04_synthese_scenarios.csv")
    fig, ax = plt.subplots(figsize=(9.5, 5))
    ax.grid(axis="y", zorder=0)

    x = np.arange(len(table))
    largeur = 0.26
    for i, seuil in enumerate(SEUILS_MINUTES):
        valeurs = table[f"part_{seuil}min"] * 100
        ax.bar(
            x + (i - 1) * largeur, valeurs, largeur * 0.92,
            color=style.RAMPE_SEUILS[i], label=f"{seuil} min", zorder=3,
        )
        for xi, v in zip(x + (i - 1) * largeur, valeurs):
            ax.text(xi, v + 1.2, f"{v:.0f}", ha="center", fontsize=8.5,
                    color=style.ENCRE_SECONDAIRE)

    # Étiquettes courtes : les libellés complets des scénarios sont dans le
    # tableau exporté, les répéter sous six groupes de barres les rendrait
    # illisibles.
    courts = {
        "Référence, réseau et offre intacts": "Référence",
        "B. Encerclement de la ZMPP": "B\nencerclement\nde la ZMPP",
        "C. A et B cumulés": "C\nA + B",
        "D. Fermeture des hôpitaux de la ZMPP": "D\nhôpitaux ZMPP\nfermés",
        "E. C et D cumulés": "E\nC + D",
    }
    ax.set_xticks(x)
    ax.set_xticklabels(
        [courts.get(s, s.replace(". ", "\n").replace(" points", "\npoints"))
         for s in table["scenario"]],
        fontsize=8.5,
    )
    ax.set_ylabel("Demande obstétricale couverte (%)")
    ax.set_ylim(0, 108)
    ax.legend(
        title="Seuil de trajet", labelcolor=style.ENCRE_SECONDAIRE, ncol=3,
        loc="upper right", bbox_to_anchor=(1.0, 1.02),
    )
    style.titrer(
        ax,
        "Choc de réseau et choc d'offre ne se lisent pas au même seuil",
        "La fermeture des hôpitaux métropolitains (D) fait chuter la barre des 30 minutes "
        "de 57 à 45 % sans presque toucher celle des 120 : elle éloigne sans couper.",
    )
    enregistrer(fig, "fig06_synthese_scenarios.png")


def fig_communes_touchees() -> None:
    """Communes classées par volume de demande perdue."""
    impact = pd.read_csv(TABLEAUX / "04_impact_par_commune.csv").head(15)
    impact = impact.sort_values("demande_decrochee")

    fig, ax = plt.subplots(figsize=(9, 6))
    ax.grid(axis="x", zorder=0)
    ax.barh(impact["commune"], impact["demande_decrochee"], color=style.SERIE_1,
            height=0.72, zorder=3)
    for y, (v, part) in enumerate(zip(impact["demande_decrochee"], impact["part_decrochee"])):
        ax.text(v * 1.02, y, f"{v:,.0f}  ({part:.0%})".replace(",", " "),
                va="center", fontsize=8.5, color=style.ENCRE_SECONDAIRE)

    ax.set_xlabel(f"Femmes de 15 à 49 ans perdant l'accès sous {SEUIL_REFERENCE} minutes")
    style.titrer(
        ax,
        "La perte est concentrée sur l'axe Port-au-Prince - Saint-Marc",
        "Quinze communes les plus touchées par le scénario combiné. Le pourcentage indique "
        "la part de la demande communale qui bascule.",
    )
    ax.margins(x=0.20)
    enregistrer(fig, "fig07_communes_touchees.png")


# Fonds de carte séparés en deux couches. Le fond sans étiquettes passe sous le
# choroplèthe, les étiquettes repassent au-dessus dans un calque dédié. Sans
# cette séparation, les noms de villes se retrouvent enfouis sous les aplats,
# puisque Leaflet place toutes les tuiles dans un plan inférieur aux polygones.
TUILES_FOND = "https://{s}.basemaps.cartocdn.com/light_nolabels/{z}/{x}/{y}{r}.png"
TUILES_ETIQUETTES = "https://{s}.basemaps.cartocdn.com/light_only_labels/{z}/{x}/{y}{r}.png"
ATTRIBUTION = (
    '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>, '
    '&copy; <a href="https://carto.com/attributions">CARTO</a>'
)


def _legende_html(sans_couverture: int) -> str:
    """
    Bandeau réunissant titre, échelle de couleur et notice de lecture.

    L'échelle est dessinée ici plutôt que par la barre de couleur de branca, qui
    se place d'autorité en haut à droite et vient buter contre le sélecteur de
    couches. La rassembler avec le texte qui l'explique évite au lecteur de
    chercher la clé de lecture à l'autre bout de l'écran.
    """
    degrade = ", ".join(style.RAMPE_BLEUE)
    return f"""
    <div style="position: fixed; top: 12px; left: 60px; z-index: 900;
                background: {style.SURFACE}; padding: 14px 16px 12px; width: 360px;
                border: 1px solid rgba(11,11,11,0.12); border-radius: 4px;
                font-family: 'Segoe UI', system-ui, sans-serif;
                box-shadow: 0 2px 10px rgba(11,11,11,0.12);">
      <div style="font-size: 15px; font-weight: 600; color: {style.ENCRE_PRINCIPALE};
                  margin-bottom: 4px;">
        Accès aux soins obstétricaux d'urgence, Haïti
      </div>
      <div style="font-size: 11.5px; color: {style.ENCRE_ATTENUEE}; margin-bottom: 10px;">
        Cas d'école, Santé Commune Initiative
      </div>

      <div style="font-size: 11.5px; color: {style.ENCRE_SECONDAIRE}; margin-bottom: 4px;">
        Demande obstétricale à plus de {SEUIL_REFERENCE} minutes d'un hôpital
      </div>
      <div style="height: 12px; border-radius: 2px; border: 1px solid rgba(11,11,11,0.10);
                  background: linear-gradient(to right, {degrade});"></div>
      <div style="display: flex; justify-content: space-between; font-size: 10.5px;
                  color: {style.ENCRE_ATTENUEE}; margin-top: 3px; margin-bottom: 12px;">
        <span>0 %</span><span>25</span><span>50</span><span>75</span><span>100 %</span>
      </div>

      <div style="font-size: 12px; color: {style.ENCRE_SECONDAIRE}; line-height: 1.45;">
        {sans_couverture} communes sont intégralement hors de portée. Survolez une commune
        pour son détail, activez les couches en haut à droite.
        <br><br>
        <span style="color: {style.STATUT_CRITIQUE};">&#9646;</span>
        Les points de contrôle sont un produit du modèle, calculé par une règle explicite,
        et non une observation de barrages existants.
      </div>
    </div>
    """


def carte_interactive(communes, structures, controles, critiques, cellules) -> None:
    """Carte html : déficit communal, offre, tronçons critiques et impact simulé."""
    import folium
    from branca.colormap import LinearColormap
    from folium.map import CustomPane
    from folium.plugins import Fullscreen

    acces = pd.read_csv(TABLEAUX / "03_accessibilite_par_commune.csv")
    impact = pd.read_csv(TABLEAUX / "04_impact_par_commune.csv")
    colonne = f"part_{SEUIL_REFERENCE}min_sonuc"

    carte_gdf = (
        communes.merge(acces[["pcode", colonne, "mediane_sonuc_min", "demande"]],
                       on="pcode", how="left")
        .merge(impact[["pcode", "demande_decrochee", "part_decrochee"]],
               on="pcode", how="left")
    )
    # Simplification à 100 m : sous l'épaisseur du trait à toute échelle utile,
    # et le fichier html passe de plusieurs mégaoctets à une taille raisonnable.
    carte_gdf["geometry"] = carte_gdf.geometry.simplify(100)
    carte_gdf = carte_gdf.to_crs("EPSG:4326")
    carte_gdf["deficit"] = 1 - carte_gdf[colonne]
    carte_gdf["pct_hors"] = (carte_gdf["deficit"] * 100).round(1)
    carte_gdf["mediane"] = carte_gdf["mediane_sonuc_min"].round(0)
    carte_gdf["demande_arrondie"] = carte_gdf["demande"].round(0)
    carte_gdf["decrochee_arrondie"] = carte_gdf["demande_decrochee"].fillna(0).round(0)
    sans_couverture = int((carte_gdf[colonne] == 0).sum())

    m = folium.Map(
        tiles=None,
        control_scale=True,          # échelle métrique en bas à gauche
        prefer_canvas=True,          # rendu canvas : indispensable avec 700 marqueurs
    )
    # Cadrage sur l'emprise réelle du pays plutôt que sur un niveau de zoom fixe :
    # un zoom en dur donne un cadrage juste sur l'écran de celui qui l'a choisi,
    # et laisse Cuba occuper la moitié de l'image sur tous les autres.
    ouest, sud, est, nord = carte_gdf.total_bounds
    m.fit_bounds([[sud, ouest], [nord, est]], padding=(12, 12))
    folium.TileLayer(
        tiles=TUILES_FOND, attr=ATTRIBUTION, name="Fond de carte", control=False
    ).add_to(m)

    # La rampe sert au calcul des couleurs ; son rendu de légende est repris à la
    # main dans le bandeau, voir _legende_html.
    echelle = LinearColormap(colors=style.RAMPE_BLEUE, vmin=0, vmax=100)

    def style_commune(entite):
        valeur = entite["properties"]["pct_hors"]
        return {
            "fillColor": style.FOND_TERRE if valeur is None else echelle(valeur),
            "color": "#ffffff", "weight": 0.7, "fillOpacity": 0.72,
        }

    folium.GeoJson(
        carte_gdf,
        name="Déficit d'accès par commune",
        style_function=style_commune,
        highlight_function=lambda f: {"weight": 2.2, "color": style.ENCRE_PRINCIPALE},
        tooltip=folium.GeoJsonTooltip(
            fields=["commune", "departement", "pct_hors", "mediane",
                    "demande_arrondie", "decrochee_arrondie"],
            aliases=["Commune", "Département",
                     f"Demande à plus de {SEUIL_REFERENCE} min (%)",
                     "Temps médian vers un hôpital (min)",
                     "Femmes de 15 à 49 ans",
                     "Dont décrochées, scénario combiné"],
            localize=True, sticky=False,
        ),
    ).add_to(m)

    # ---- Tronçons critiques -------------------------------------------------
    critiques = critiques.to_crs("EPSG:4326").nlargest(400, "charge_demande")
    charge_max = critiques["charge_demande"].max()
    groupe_t = folium.FeatureGroup(name="Tronçons les plus chargés", show=False).add_to(m)
    for _, r in critiques.iterrows():
        folium.PolyLine(
            [(y, x) for x, y in r.geometry.coords],
            color=style.SERIE_1,
            weight=1.5 + 4.5 * (r["charge_demande"] / charge_max) ** 0.5,
            opacity=0.8,
            tooltip=f"{r['classe']} — charge : {r['charge_demande']:,.0f} femmes".replace(",", " "),
        ).add_to(groupe_t)

    # ---- Cellules décrochées ------------------------------------------------
    perdues = cellules[cellules["decrochee"]]
    groupe_p = folium.FeatureGroup(
        name=f"Demande décrochée, scénario combiné ({len(perdues)} cellules)", show=True
    ).add_to(m)
    for _, r in perdues.iterrows():
        folium.CircleMarker(
            [r["y"], r["x"]], radius=3, color=style.STATUT_CRITIQUE,
            fill=True, fill_opacity=0.55, weight=0,
            tooltip=(
                f"{r['commune']} — {r['demande_obstetricale']:,.0f} femmes, "
                f"{r['minutes_perdues']:,.0f} min perdues".replace(",", " ")
            ),
        ).add_to(groupe_p)

    # ---- Offre --------------------------------------------------------------
    sonuc = structures[structures["niveau"] == "SONUC"].to_crs("EPSG:4326")
    groupe_h = folium.FeatureGroup(name=f"Hôpitaux SONUC ({len(sonuc)})").add_to(m)
    for _, r in sonuc.iterrows():
        folium.CircleMarker(
            [r.geometry.y, r.geometry.x], radius=4,
            color=style.ENCRE_PRINCIPALE, fill=True, fill_color="#ffffff",
            fill_opacity=1.0, weight=1.6,
            tooltip=str(r.get("nom") or "Hôpital sans nom renseigné"),
        ).add_to(groupe_h)

    # ---- Points de contrôle simulés ----------------------------------------
    noms = communes.set_index("pcode")["commune"]
    groupe_c = folium.FeatureGroup(
        name=f"Points de contrôle simulés ({len(controles)})"
    ).add_to(m)

    # Classés par dommage décroissant : le rang porté par la pastille est
    # l'information utile, un tronçon isolé sur la carte ne dit pas ce qu'il
    # coûte. Le tronçon lui-même mesure quelques dizaines de mètres et
    # disparaîtrait sans cette pastille.
    ordonnes = controles.to_crs("EPSG:4326").sort_values(
        "demande_decrochee", ascending=False
    ).reset_index(drop=True)

    for rang, r in ordonnes.iterrows():
        commune = noms.get(r["commune"], "commune non identifiée")
        infobulle = (
            f"<b>Point de contrôle simulé n&deg; {rang + 1}</b><br>{commune}<br>"
            f"Classe de route : {r['classe']}<br><br>"
            f"Sa coupure fait basculer <b>{r['demande_decrochee']:,.0f} femmes</b> "
            f"au-delà de {SEUIL_REFERENCE} minutes.".replace(",", " ")
        )
        milieu = r.geometry.interpolate(0.5, normalized=True)

        folium.PolyLine(
            [(y, x) for x, y in r.geometry.coords],
            color=style.STATUT_CRITIQUE, weight=6, opacity=0.95,
        ).add_to(groupe_c)
        folium.CircleMarker(
            [milieu.y, milieu.x], radius=9,
            color=style.STATUT_CRITIQUE, fill=True, fill_color=style.STATUT_CRITIQUE,
            fill_opacity=0.30, weight=2.2,
            tooltip=f"n° {rang + 1} — {r['demande_decrochee']:,.0f} femmes".replace(",", " "),
            popup=folium.Popup(infobulle, max_width=280),
        ).add_to(groupe_c)

    # ---- Étiquettes au-dessus des aplats ------------------------------------
    CustomPane("etiquettes", z_index=650, pointer_events=False).add_to(m)
    folium.TileLayer(
        tiles=TUILES_ETIQUETTES, attr=ATTRIBUTION, name="Noms de lieux",
        overlay=True, control=True, pane="etiquettes",
    ).add_to(m)

    Fullscreen(title="Plein écran", title_cancel="Quitter le plein écran").add_to(m)
    folium.LayerControl(collapsed=False).add_to(m)
    m.get_root().html.add_child(folium.Element(_legende_html(sans_couverture)))

    chemin = FIGURES.parent / "carte_interactive.html"
    m.save(str(chemin))
    log(f"carte interactive écrite : {chemin.name} ({chemin.stat().st_size / 1e6:.1f} Mo)")


def main() -> None:
    style.appliquer()
    with etape("chargement des couches"):
        cellules, communes, structures, controles, critiques = charger()

    with etape("cartes"):
        fig_accessibilite(cellules, communes, structures)
        fig_couverture_communes(communes)
        fig_troncons_critiques(communes, critiques, controles)
        fig_impact(cellules, communes)

    with etape("graphiques"):
        fig_courbe_degradation()
        fig_synthese_scenarios()
        fig_communes_touchees()

    with etape("carte interactive"):
        carte_interactive(communes, structures, controles, critiques, cellules)

    log("étape 5 terminée")


if __name__ == "__main__":
    main()
