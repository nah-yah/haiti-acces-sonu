"""
Noyau de calcul d'accessibilité, partagé par l'analyse de référence et les
scénarios de blocage.

Dijkstra multi-sources : plutôt qu'un plus court chemin depuis chacune des
dizaines de milliers de cellules, on part simultanément de toutes les structures
et on propage vers le réseau. Le graphe étant non orienté, un seul parcours donne
en tout point le temps vers la structure la plus proche.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components, dijkstra
from scipy.spatial import cKDTree

from config import (
    DISTANCE_MAX_RATTACHEMENT_M,
    FACTEUR_DETOUR,
    VITESSE_ACCES_KMH,
)


@dataclass
class Graphe:
    """Réseau routier prêt pour le calcul de plus courts chemins."""

    x: np.ndarray            # abscisse des sommets, en mètres
    y: np.ndarray            # ordonnée des sommets, en mètres
    u: np.ndarray            # sommet origine de chaque arête
    v: np.ndarray            # sommet destination de chaque arête
    temps: np.ndarray        # temps de parcours de l'arête, en minutes
    longueur: np.ndarray
    classe: np.ndarray
    ux: np.ndarray
    uy: np.ndarray
    vx: np.ndarray
    vy: np.ndarray

    @property
    def n_sommets(self) -> int:
        return len(self.x)

    def arbre(self) -> cKDTree:
        if not hasattr(self, "_arbre"):
            self._arbre = cKDTree(np.column_stack([self.x, self.y]))
        return self._arbre

    def _dedoublonner(self) -> None:
        """
        Regroupe une fois pour toutes les arêtes reliant le même couple de
        sommets, en retenant la plus rapide.

        Laisser scipy sommer les doublons gonflerait le temps de parcours. Le
        regroupement coûte cher et ne dépend pas du scénario : le refaire à
        chaque évaluation dominerait le coût d'une simulation.
        """
        if hasattr(self, "_groupes"):
            return

        a = np.minimum(self.u, self.v)
        b = np.maximum(self.u, self.v)
        cle = a.astype("int64") * self.n_sommets + b
        ordre = np.argsort(cle, kind="stable")

        cle_triee = cle[ordre]
        debut_groupe = np.empty(len(cle), dtype=bool)
        debut_groupe[0] = True
        np.not_equal(cle_triee[1:], cle_triee[:-1], out=debut_groupe[1:])
        groupe_trie = np.cumsum(debut_groupe) - 1

        self._groupes = np.empty(len(cle), dtype="int64")
        self._groupes[ordre] = groupe_trie
        self._ordre_par_groupe = ordre
        self._debuts = np.flatnonzero(debut_groupe)
        self._fins = np.append(self._debuts[1:], len(cle))

        self._grp_a = a[ordre][self._debuts]
        self._grp_b = b[ordre][self._debuts]
        self._grp_t = np.minimum.reduceat(self.temps[ordre], self._debuts)

    def matrice(self, aretes_coupees: np.ndarray | None = None) -> coo_matrix:
        """
        Matrice creuse du graphe, en minutes.

        `aretes_coupees` est un masque booléen : les arêtes marquées sont
        retirées du réseau. Un point de contrôle est simulé par retrait et non
        par ralentissement, un barrage tenu ne se franchissant pas au ralenti.
        """
        self._dedoublonner()
        temps = self._grp_t.copy()

        if aretes_coupees is not None and aretes_coupees.any():
            # Seuls les groupes touchés sont recalculés. Si deux tronçons
            # relient le même couple et qu'un seul est coupé, le lien subsiste.
            touches = np.unique(self._groupes[aretes_coupees])
            for g in touches:
                membres = self._ordre_par_groupe[self._debuts[g]:self._fins[g]]
                survivants = membres[~aretes_coupees[membres]]
                temps[g] = self.temps[survivants].min() if len(survivants) else np.inf

            vivant = np.isfinite(temps)
            return coo_matrix(
                (temps[vivant], (self._grp_a[vivant], self._grp_b[vivant])),
                shape=(self.n_sommets, self.n_sommets),
            ).tocsr()

        return coo_matrix(
            (temps, (self._grp_a, self._grp_b)),
            shape=(self.n_sommets, self.n_sommets),
        ).tocsr()


def charger_graphe(chemin) -> Graphe:
    d = np.load(chemin, allow_pickle=False)
    return Graphe(
        x=d["sommets_x"], y=d["sommets_y"],
        u=d["u"].astype("int64"), v=d["v"].astype("int64"),
        temps=d["temps_min"].astype("float64"),
        longueur=d["longueur_m"].astype("float64"),
        classe=d["classe"],
        ux=d["ux"], uy=d["uy"], vx=d["vx"], vy=d["vy"],
    )


def rattacher(graphe: Graphe, x: np.ndarray, y: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """
    Rattache des points au sommet routier le plus proche.

    Retourne l'indice du sommet et le temps du segment terminal, en minutes.
    Au-delà de DISTANCE_MAX_RATTACHEMENT_M le temps vaut l'infini : le point est
    hors de portée du réseau carrossable.
    """
    distance, sommet = graphe.arbre().query(np.column_stack([x, y]), k=1)
    minutes = distance * FACTEUR_DETOUR / (VITESSE_ACCES_KMH * 1000.0 / 60.0)
    minutes = np.where(distance > DISTANCE_MAX_RATTACHEMENT_M, np.inf, minutes)
    return sommet.astype("int64"), minutes


def temps_vers_offre(
    graphe: Graphe,
    sommets_offre: np.ndarray,
    sommets_demande: np.ndarray,
    minutes_acces: np.ndarray,
    aretes_coupees: np.ndarray | None = None,
    avec_chemins: bool = False,
):
    """
    Temps de trajet de chaque point de demande vers l'offre la plus proche.

    Minutes, infini si aucune structure n'est atteignable par la route. Si
    demandé, les prédécesseurs et sources permettant de reconstituer les
    itinéraires.
    """
    matrice = graphe.matrice(aretes_coupees)
    resultat = dijkstra(
        matrice,
        directed=False,
        indices=np.unique(sommets_offre),
        min_only=True,
        return_predecessors=avec_chemins,
    )
    if avec_chemins:
        distances, predecesseurs, sources = resultat
    else:
        distances, predecesseurs, sources = resultat, None, None

    minutes = minutes_acces + distances[sommets_demande]
    return minutes, predecesseurs, sources


def flux_par_arete(
    graphe: Graphe,
    sommets_demande: np.ndarray,
    poids: np.ndarray,
    predecesseurs: np.ndarray,
) -> np.ndarray:
    """
    Charge de demande portée par chaque arête du réseau.

    On remonte l'itinéraire de chaque cellule vers sa structure de rattachement
    et on cumule sa demande obstétricale sur les tronçons empruntés. C'est cette
    charge, et non la centralité topologique, qui sert de présélection.
    """
    n = graphe.n_sommets
    charge_sommet_paire: dict[tuple[int, int], float] = {}

    for sommet_depart, poids_i in zip(sommets_demande, poids):
        if not np.isfinite(poids_i) or poids_i <= 0:
            continue
        courant = int(sommet_depart)
        precedent = predecesseurs[courant]
        garde_fou = 0
        while precedent >= 0 and garde_fou < 100_000:
            cle = (courant, precedent) if courant < precedent else (precedent, courant)
            charge_sommet_paire[cle] = charge_sommet_paire.get(cle, 0.0) + float(poids_i)
            courant = int(precedent)
            precedent = predecesseurs[courant]
            garde_fou += 1

    # Report de la charge, indexée par paire de sommets, vers les arêtes.
    a = np.minimum(graphe.u, graphe.v)
    b = np.maximum(graphe.u, graphe.v)
    charge = np.zeros(len(graphe.u), dtype="float64")
    if charge_sommet_paire:
        cles = np.array(list(charge_sommet_paire.keys()), dtype="int64")
        valeurs = np.array(list(charge_sommet_paire.values()), dtype="float64")
        table = pd.Series(
            valeurs, index=pd.MultiIndex.from_arrays([cles[:, 0], cles[:, 1]])
        )
        recherche = pd.MultiIndex.from_arrays([a, b])
        charge = table.reindex(recherche).fillna(0.0).to_numpy()
    return charge


def composantes(graphe: Graphe) -> np.ndarray:
    """Composantes connexes du réseau, pour repérer les sous-réseaux insulaires."""
    n_comp, etiquettes = connected_components(graphe.matrice(), directed=False)
    return etiquettes


def mediane_ponderee(valeurs: np.ndarray, poids: np.ndarray) -> float:
    """
    Médiane pondérée, sur les seules valeurs finies.

    Préférée à la moyenne : la distribution des temps est très dissymétrique et
    quelques cellules isolées tirent la moyenne loin de la population type.
    """
    valeurs = np.asarray(valeurs, dtype="float64")
    poids = np.asarray(poids, dtype="float64")
    fini = np.isfinite(valeurs) & np.isfinite(poids) & (poids > 0)
    if not fini.any():
        return np.nan

    v, p = valeurs[fini], poids[fini]
    ordre = np.argsort(v)
    v, p = v[ordre], p[ordre]
    cumul = np.cumsum(p)
    return float(v[np.searchsorted(cumul, cumul[-1] / 2.0)])


def indicateurs(
    minutes: np.ndarray, poids: np.ndarray, seuils: tuple[int, ...]
) -> dict[str, float]:
    """Part de la demande couverte à chaque seuil, et temps médian pondéré."""
    total = poids.sum()
    resultat = {"demande_totale": total}
    for seuil in seuils:
        couvert = poids[minutes <= seuil].sum()
        resultat[f"part_{seuil}min"] = couvert / total if total else np.nan
    atteignable = np.isfinite(minutes)
    resultat["part_non_atteignable"] = poids[~atteignable].sum() / total if total else np.nan
    resultat["mediane_min"] = mediane_ponderee(minutes, poids)
    return resultat
