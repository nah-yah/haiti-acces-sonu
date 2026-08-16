"""Utilitaires transversaux : journalisation, détection de colonnes, chronométrage."""

from __future__ import annotations

import re
import sys
import time
import unicodedata
from contextlib import contextmanager

import pandas as pd


def log(message: str) -> None:
    """Écrit un message horodaté sur la sortie standard."""
    print(f"[{time.strftime('%H:%M:%S')}] {message}", flush=True)


@contextmanager
def etape(nom: str):
    """Encadre une étape et affiche sa durée."""
    log(f"-> {nom}")
    debut = time.perf_counter()
    try:
        yield
    finally:
        log(f"   {nom} : {time.perf_counter() - debut:.1f} s")


def normaliser(texte: str) -> str:
    """Minuscules sans accents ni ponctuation, pour comparer des libellés."""
    if texte is None:
        return ""
    sans_accent = unicodedata.normalize("NFKD", str(texte))
    sans_accent = "".join(c for c in sans_accent if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", "", sans_accent.lower())


def trouver_colonne(colonnes, *motifs: str) -> str:
    """
    Retourne la première colonne dont le nom normalisé contient l'un des motifs.

    Les exports OCHA et HOT OSM changent de casse et de séparateurs d'une version
    à l'autre (`ADM2_PCODE`, `adm2_pcode`, `Admin2 Pcode`). Chercher par motif
    évite de casser le pipeline à chaque mise à jour du jeu source.
    """
    normalisees = {normaliser(c): c for c in colonnes}
    for motif in motifs:
        cible = normaliser(motif)
        if cible in normalisees:
            return normalisees[cible]
    for motif in motifs:
        cible = normaliser(motif)
        for norm, brut in normalisees.items():
            if cible in norm:
                return brut
    raise KeyError(
        f"Aucune colonne ne correspond à {motifs}. Colonnes disponibles : {list(colonnes)}"
    )


def formater_milliers(valeur: float, decimales: int = 0) -> str:
    """
    Formate un nombre avec le point comme séparateur de milliers.

    Convention francophone haïtienne retenue dans les livrables du projet.
    """
    if pd.isna(valeur):
        return "n.d."
    texte = f"{valeur:,.{decimales}f}"
    return texte.replace(",", " ").replace(" ", ".")


def exiger(condition: bool, message: str) -> None:
    """Interrompt le script avec un message lisible si la condition est fausse."""
    if not condition:
        log(f"ECHEC : {message}")
        sys.exit(1)
