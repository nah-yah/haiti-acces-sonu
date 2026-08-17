# %% [markdown]
# # Figures d'accompagnement de la documentation
#
# Ce carnet ne refait aucun calcul de l'analyse. Il relit les sorties de la
# chaîne et produit quatre figures qui expliquent *comment* le projet est
# construit, là où `p05_cartes.py` produit les figures de résultat.
#
# | Figure | Ce qu'elle montre |
# | --- | --- |
# | `fig_doc01_topologie` | D'où vient la topologie du graphe, et ce que l'arrondi y ajoute |
# | `fig_doc02_charge_criticite` | Que la charge d'un tronçon ne dit pas ce que sa coupure coûte |
# | `fig_doc03_graphe_zoom` | À quoi ressemble le graphe de près |
# | `fig_doc04_impact_troncon` | Qui paie la coupure du tronçon le plus critique |
#
# Prérequis : la chaîne doit avoir tourné au moins une fois, `run_all.py`.

# %%
from __future__ import annotations

import json
import sys
from pathlib import Path

import geopandas as gpd
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import shapely
from matplotlib.lines import Line2D

RACINE = Path.cwd().parent if Path.cwd().name == "notebooks" else Path.cwd()
sys.path.insert(0, str(RACINE / "src"))

import style  # noqa: E402
from acces import charger_graphe, temps_vers_offre  # noqa: E402
from config import (  # noqa: E402
    CLASSES_EXCLUES, CRS_METRIQUE, DATA_TRAITE, DPI_FIGURES,
    FIGURES, TABLEAUX, VITESSES_KMH,
)

style.appliquer()
print(f"racine : {RACINE}")

# %% [markdown]
# ## 1. Ce qui fait la topologie du réseau
#
# Une pile de polylignes n'est pas un graphe. Tant que les tronçons sont des
# objets indépendants, aucun plus court chemin n'est calculable : il faut que
# deux tronçons qui se rejoignent partagent le même sommet.
#
# Le passage se fait par un dédoublonnage des points de forme. On mesure ici ce
# que chaque opération apporte réellement, avec le même filtrage de classes que
# `p02_construire_graphe.py`, sans quoi les chiffres ne seraient pas comparables
# à ceux du graphe livré.

# %%
# Ce décompte relit tout le réseau et trie 1,4 million de coordonnées : deux à
# trois minutes. Le résultat ne dépend que du fichier source, donc on le met en
# cache pour que réajuster une figure ne coûte plus que quelques secondes.
CACHE = DATA_TRAITE / "doc_comptage_sommets.json"

if CACHE.exists():
    comptage = json.loads(CACHE.read_text(encoding="utf-8"))
    print(f"comptage relu depuis {CACHE.name}")
else:
    routes = gpd.read_file(DATA_TRAITE.parent / "raw" / "roads.gpkg")
    col_classe = [c for c in routes.columns if c.lower() == "highway"][0]
    routes = routes.rename(columns={col_classe: "classe"})
    routes["classe"] = routes["classe"].fillna("unclassified").astype(str).str.lower()
    # Mêmes exclusions que p02 : un transfert obstétrical n'emprunte pas un escalier.
    routes = routes[~routes["classe"].isin(CLASSES_EXCLUES)]
    routes = routes[routes["classe"].isin(VITESSES_KMH)]
    routes = routes.to_crs(CRS_METRIQUE)
    routes = routes.explode(index_parts=False, ignore_index=True)
    routes = routes[routes.geometry.geom_type == "LineString"]

    coords = shapely.get_coordinates(routes.geometry.values)
    comptage = {
        "n_points": int(len(coords)),
        "n_exact": int(len(np.unique(coords, axis=0))),
        "n_arrondi": int(len(np.unique(np.round(coords).astype(np.int64), axis=0))),
    }
    CACHE.write_text(json.dumps(comptage, indent=2), encoding="utf-8")
    print(f"comptage calculé puis écrit dans {CACHE.name}")

n_points = comptage["n_points"]
n_exact = comptage["n_exact"]
n_arrondi = comptage["n_arrondi"]

fusions_exactes = n_points - n_exact
soudes = n_exact - n_arrondi
print(f"points de forme lus              : {n_points:,}".replace(",", " "))
print(f"sommets, dédoublonnage exact     : {n_exact:,}".replace(",", " "))
print(f"sommets, arrondi au mètre        : {n_arrondi:,}".replace(",", " "))
print()
print(f"fusions dues au dédoublonnage    : {fusions_exactes:,}".replace(",", " "))
print(f"fusions ajoutées par l'arrondi   : {soudes:,}".replace(",", " "))
print(f"part de l'arrondi dans le total  : {100 * soudes / (fusions_exactes + soudes):.2f} %")

# %%
graphe = charger_graphe(DATA_TRAITE / "graphe.npz")
degre = np.bincount(np.concatenate([graphe.u, graphe.v]), minlength=graphe.n_sommets)
print(f"graphe : {graphe.n_sommets:,} sommets, {len(graphe.u):,} arêtes".replace(",", " "))
print(f"degré médian {np.median(degre):.0f}, sommets de degré >= 4 : {(degre >= 4).sum():,}".replace(",", " "))

# %%
fig, (ga, gb) = plt.subplots(1, 2, figsize=(11.5, 4.6), gridspec_kw={"width_ratios": [1, 1.15]})

# -- panneau gauche : d'ou vient reellement la topologie
# Deux barres empilees plutot que trois barres separees : ce qui compte n'est
# pas le niveau de chaque denombrement mais la taille relative des deux
# fusions, et l'arrondi ne pese presque rien.
ga.barh([0], [fusions_exactes], color=style.SERIE_1, height=0.5,
        label=f"dédoublonnage exact  {fusions_exactes:,}".replace(",", " "))
ga.barh([0], [soudes], left=[fusions_exactes], color=style.SERIE_2, height=0.5,
        label=f"arrondi au mètre  {soudes:,}".replace(",", " "))
ga.annotate(
    f"{soudes} sommets, soit "
    + f"{100 * soudes / (fusions_exactes + soudes):.2f}".replace(".", ",")
    + " % des fusions\n(invisible à cette échelle)",
    xy=(fusions_exactes + soudes, 0), xytext=(fusions_exactes * 0.66, 0.42),
    fontsize=9, color=style.ENCRE_PRINCIPALE,
    arrowprops=dict(arrowstyle="-", color=style.ENCRE_ATTENUEE, lw=0.9),
)
ga.set_ylim(-0.55, 0.62)
ga.set_yticks([])
ga.set_xlabel("points de forme fusionnés en un sommet partagé")
ga.xaxis.set_major_formatter(lambda v, _: f"{v/1000:.0f}k" if v else "0")
ga.legend(loc="lower left", bbox_to_anchor=(0, -0.42), ncols=1)
style.titrer(
    ga,
    "L'arrondi n'est qu'un filet de sécurité",
    "Sur " + f"{n_points:,}".replace(",", " ")
    + " points de forme, le dédoublonnage fait tout le travail.",
)

# -- panneau droit : un carrefour reel, aretes incidentes et sommet partage
centre = int(np.argmax(np.where(degre >= 6, degre, 0)))
cx, cy = graphe.x[centre], graphe.y[centre]
fenetre = 170
proche = (
    (np.minimum(graphe.ux, graphe.vx) < cx + fenetre)
    & (np.maximum(graphe.ux, graphe.vx) > cx - fenetre)
    & (np.minimum(graphe.uy, graphe.vy) < cy + fenetre)
    & (np.maximum(graphe.uy, graphe.vy) > cy - fenetre)
)
idx = np.nonzero(proche)[0]
incidentes = (graphe.u == centre) | (graphe.v == centre)

for i in idx:
    gb.plot([graphe.ux[i], graphe.vx[i]], [graphe.uy[i], graphe.vy[i]],
            color=style.LIGNE_BASE, lw=1.6, zorder=1, solid_capstyle="round")
for n, i in enumerate(np.nonzero(incidentes)[0]):
    gb.plot([graphe.ux[i], graphe.vx[i]], [graphe.uy[i], graphe.vy[i]],
            color=[style.SERIE_1, style.SERIE_2, style.STATUT_BON,
                   style.STATUT_ALERTE, "#7b4fd0", "#0f8f8f"][n % 6],
            lw=2.6, zorder=2, solid_capstyle="round")

sommets_vus = np.unique(np.concatenate([graphe.u[idx], graphe.v[idx]]))
gb.scatter(graphe.x[sommets_vus], graphe.y[sommets_vus], s=13,
           color=style.SURFACE, edgecolor=style.ENCRE_ATTENUEE, lw=0.9, zorder=3)
gb.scatter([cx], [cy], s=150, facecolor="none", edgecolor=style.ENCRE_PRINCIPALE,
           lw=1.8, zorder=4)
gb.annotate(f"un seul sommet, {degre[centre]} arêtes incidentes\n"
            f"fenêtre de {2 * fenetre} m",
            xy=(cx, cy), xytext=(cx + fenetre * 0.22, cy + fenetre * 0.52),
            fontsize=9, color=style.ENCRE_PRINCIPALE,
            arrowprops=dict(arrowstyle="-", color=style.ENCRE_ATTENUEE, lw=0.9))
gb.set_xlim(cx - fenetre, cx + fenetre)
gb.set_ylim(cy - fenetre, cy + fenetre)
gb.set_aspect("equal")
# Sous-titre laisse vide : sur un panneau large et court, le titre et le
# sous-titre de habiller_carte se chevauchent. L'information de fenetre est
# passee dans l'annotation.
style.habiller_carte(gb, "Un carrefour, une fois la topologie rétablie")

fig.tight_layout(w_pad=3.0)
fig.savefig(FIGURES / "fig_doc01_topologie.png", dpi=DPI_FIGURES, bbox_inches="tight")
plt.show()

# %% [markdown]
# ## 2. La charge ne dit pas ce que la coupure coûte
#
# La présélection classe les tronçons par la demande obstétricale dont
# l'itinéraire le plus rapide les emprunte. L'évaluation directe, elle, recalcule
# l'accessibilité du pays entier sans le tronçon et mesure les minutes réellement
# perdues. Les deux classements divergent, et c'est ce que montre la figure.

# %%
crit = pd.read_csv(TABLEAUX / "04_criticite_troncons.csv")
rho = crit["charge"].rank(ascending=False).corr(
    crit["minutes_perdues_ponderees"].rank(ascending=False), method="spearman"
)
print(f"{len(crit)} tronçons évalués, corrélation de rang de Spearman : {rho:.2f}")

plus_charge = crit.loc[crit["charge"].idxmax()]
plus_couteux = crit.loc[crit["minutes_perdues_ponderees"].idxmax()]
print(f"\ntronçon le plus chargé  : arête {plus_charge['arete']:.0f}, "
      f"charge {plus_charge['charge']:,.0f}, dommage {plus_charge['minutes_perdues_ponderees']:,.0f}"
      .replace(",", " "))
print(f"tronçon le plus coûteux : arête {plus_couteux['arete']:.0f}, "
      f"charge {plus_couteux['charge']:,.0f}, dommage {plus_couteux['minutes_perdues_ponderees']:,.0f}"
      .replace(",", " "))

# %%
fig, ax = plt.subplots(figsize=(8.6, 5.4))
ax.grid(True, axis="both", lw=0.7, color=style.GRILLE, zorder=0)
ax.scatter(crit["charge"] / 1000, crit["minutes_perdues_ponderees"] / 1000,
           s=64, color=style.SERIE_1, alpha=0.85, edgecolor=style.SURFACE, lw=1.0, zorder=3)

for ligne, texte, dx, dy in [
    (plus_couteux, "le plus coûteux :\n19 689 femmes décrochées", 0.06, -0.10),
    (plus_charge, "le plus chargé,\nmais contournable", -0.02, 0.16),
]:
    ax.scatter([ligne["charge"] / 1000], [ligne["minutes_perdues_ponderees"] / 1000],
               s=110, facecolor="none", edgecolor=style.STATUT_CRITIQUE, lw=1.8, zorder=4)
    ax.annotate(
        texte,
        xy=(ligne["charge"] / 1000, ligne["minutes_perdues_ponderees"] / 1000),
        xytext=(ligne["charge"] / 1000 + dx * 90, ligne["minutes_perdues_ponderees"] / 1000 + dy * 1300),
        fontsize=9, color=style.ENCRE_PRINCIPALE, ha="left",
        arrowprops=dict(arrowstyle="-", color=style.ENCRE_ATTENUEE, lw=0.9),
    )

ax.set_xlabel("charge du tronçon, en milliers de femmes 15-49 ans")
ax.set_ylabel("minutes perdues, en milliers, pondérées par la demande")
style.titrer(
    ax,
    "Corrélation de rang de seulement " + f"{rho:.2f}".replace(".", ","),
    "Chaque point est un tronçon dont la coupure a été simulée sur le réseau entier.",
    f"{len(crit)} tronçons évalués. Analyse : Santé Commune Initiative (cas d'école).",
)
fig.tight_layout()
fig.savefig(FIGURES / "fig_doc02_charge_criticite.png", dpi=DPI_FIGURES, bbox_inches="tight")
plt.show()

# %% [markdown]
# ## 3. Le graphe de près
#
# « 1,33 million de sommets » reste abstrait tant qu'on n'a pas vu à quoi
# correspond un sommet. La fenêtre ci-dessous fait 3 km de côté.

# %%
communes = gpd.read_file(DATA_TRAITE / "communes.gpkg", layer="communes").to_crs(CRS_METRIQUE)
saint_marc = communes[communes["pcode"] == "HT0531"]
cx, cy = float(saint_marc.geometry.centroid.x.iloc[0]), float(saint_marc.geometry.centroid.y.iloc[0])

fenetre = 1500
proche = (
    (np.minimum(graphe.ux, graphe.vx) < cx + fenetre)
    & (np.maximum(graphe.ux, graphe.vx) > cx - fenetre)
    & (np.minimum(graphe.uy, graphe.vy) < cy + fenetre)
    & (np.maximum(graphe.uy, graphe.vy) > cy - fenetre)
)
idx = np.nonzero(proche)[0]

EPAISSEUR = {"primary": 2.6, "secondary": 2.0, "tertiary": 1.5,
             "unclassified": 1.1, "residential": 0.9, "service": 0.6}
TEINTE = {"primary": style.SERIE_1, "secondary": "#5598e7", "tertiary": "#9ec5f4"}

fig, ax = plt.subplots(figsize=(8.2, 8.2))
for i in idx:
    c = str(graphe.classe[i])
    ax.plot([graphe.ux[i], graphe.vx[i]], [graphe.uy[i], graphe.vy[i]],
            color=TEINTE.get(c, style.LIGNE_BASE), lw=EPAISSEUR.get(c, 0.8),
            solid_capstyle="round", zorder=2)

sommets_vus = np.unique(np.concatenate([graphe.u[idx], graphe.v[idx]]))
ax.scatter(graphe.x[sommets_vus], graphe.y[sommets_vus], s=3.2,
           color=style.ENCRE_ATTENUEE, alpha=0.55, zorder=3, linewidths=0)

ax.set_xlim(cx - fenetre, cx + fenetre)
ax.set_ylim(cy - fenetre, cy + fenetre)
ax.set_aspect("equal")
ax.legend(handles=[
    Line2D([], [], color=style.SERIE_1, lw=2.6, label="primaire"),
    Line2D([], [], color="#5598e7", lw=2.0, label="secondaire"),
    Line2D([], [], color="#9ec5f4", lw=1.5, label="tertiaire"),
    Line2D([], [], color=style.LIGNE_BASE, lw=0.9, label="desserte locale"),
    Line2D([], [], color=style.ENCRE_ATTENUEE, lw=0, marker="o", ms=3, label="sommet"),
], loc="lower left", ncols=2)
style.habiller_carte(
    ax, "Le graphe routier à Saint-Marc",
    f"Fenêtre de 3 km de côté, {len(idx):,} arêtes et {len(sommets_vus):,} sommets.".replace(",", " "),
    "Source : HOT / OpenStreetMap. Analyse : Santé Commune Initiative (cas d'école).",
)
fig.tight_layout()
fig.savefig(FIGURES / "fig_doc03_graphe_zoom.png", dpi=DPI_FIGURES, bbox_inches="tight")
plt.show()

# %% [markdown]
# ## 4. Qui paie la coupure du tronçon le plus critique
#
# On recalcule l'accessibilité nationale en retirant la seule arête la plus
# coûteuse, puis on cartographie l'écart de temps de trajet, cellule par cellule.

# %%
ref = np.load(DATA_TRAITE / "reference.npz", allow_pickle=False)
cellules = pd.read_parquet(DATA_TRAITE / "cellules_reference.parquet")

arete_critique = int(plus_couteux["arete"])
masque = np.zeros(len(graphe.u), dtype=bool)
masque[arete_critique] = True

avant = cellules["minutes_sonuc"].to_numpy()
apres, _, _ = temps_vers_offre(
    graphe, ref["sommets_sonuc"], ref["sommets_demande"], ref["minutes_acces"],
    aretes_coupees=masque,
)
delta = np.where(np.isfinite(avant) & np.isfinite(apres), apres - avant, np.nan)
touchees = np.nan_to_num(delta) > 0.5
print(f"arête coupée : {arete_critique}, classe {graphe.classe[arete_critique]}")
print(f"cellules dont le trajet s'allonge : {touchees.sum():,}".replace(",", " "))
print(f"allongement maximal : {np.nanmax(delta):.0f} minutes")
print(f"demande basculant au-delà de 60 min : "
      f"{cellules['demande_obstetricale'].to_numpy()[(avant <= 60) & (apres > 60)].sum():,.0f}"
      .replace(",", " "))

# %%
fig, ax = plt.subplots(figsize=(8.6, 8.6))
communes.plot(ax=ax, facecolor=style.FOND_TERRE, edgecolor=style.SURFACE, lw=0.5, zorder=1)

vus = touchees
nuage = ax.scatter(
    cellules["xm"].to_numpy()[vus], cellules["ym"].to_numpy()[vus],
    c=np.clip(delta[vus], 0, 60), s=16, cmap=style.CMAP_TEMPS,
    vmin=0, vmax=60, zorder=3, linewidths=0,
)
ax.plot([graphe.ux[arete_critique], graphe.vx[arete_critique]],
        [graphe.uy[arete_critique], graphe.vy[arete_critique]],
        color=style.STATUT_CRITIQUE, lw=4, zorder=4, solid_capstyle="round")

marge = 12_000
xs = cellules["xm"].to_numpy()[vus]
ys = cellules["ym"].to_numpy()[vus]
ax.set_xlim(xs.min() - marge, xs.max() + marge)
ax.set_ylim(ys.min() - marge, ys.max() + marge)
ax.set_aspect("equal")

barre = fig.colorbar(nuage, ax=ax, shrink=0.42, pad=0.01)
barre.set_label("minutes ajoutées au trajet", fontsize=9, color=style.ENCRE_SECONDAIRE)
barre.outline.set_visible(False)
ax.legend(handles=[Line2D([], [], color=style.STATUT_CRITIQUE, lw=4, label="tronçon coupé")],
          loc="lower left")
style.habiller_carte(
    ax, "Un seul tronçon coupé, et voilà qui paie",
    f"{touchees.sum():,} cellules voient leur trajet s'allonger.".replace(",", " "),
    "Sources : HOT / OpenStreetMap, WorldPop 2020, OCHA COD 2024. "
    "Analyse : Santé Commune Initiative (cas d'école).",
)
fig.tight_layout()
fig.savefig(FIGURES / "fig_doc04_impact_troncon.png", dpi=DPI_FIGURES, bbox_inches="tight")
plt.show()

# %% [markdown]
# ## Récapitulatif des chiffres cités dans la documentation

# %%
recap = pd.DataFrame([
    ("Points de forme lus", f"{n_points:,}"),
    ("Sommets après arrondi au mètre", f"{n_arrondi:,}"),
    ("Fusions dues au dédoublonnage exact", f"{fusions_exactes:,}"),
    ("Fusions ajoutées par l'arrondi", f"{soudes:,}"),
    ("Arêtes du graphe", f"{len(graphe.u):,}"),
    ("Longueur du réseau (km)", f"{graphe.longueur.sum()/1000:,.0f}"),
    ("Tronçons évalués un par un", f"{len(crit)}"),
    ("Corrélation de rang charge / dommage", f"{rho:.2f}"),
    ("Cellules touchées par la coupure la plus coûteuse", f"{touchees.sum():,}"),
], columns=["grandeur", "valeur"])
recap["valeur"] = recap["valeur"].str.replace(",", " ", regex=False)
recap.to_csv(TABLEAUX / "doc_recapitulatif.csv", index=False, encoding="utf-8-sig")
print(recap.to_string(index=False))
