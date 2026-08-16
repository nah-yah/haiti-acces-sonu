"""
Exécute la chaîne complète, du téléchargement aux cartes.

    python run_all.py              chaîne complète
    python run_all.py --depuis 3   reprend à l'étape 3
    python run_all.py --etape 4    n'exécute que l'étape 4

Chaque étape écrit ses sorties sur disque et lit celles de la précédente, ce qui
permet de reprendre à mi-parcours sans tout recalculer. Le calcul le plus long
est l'étape 2, la construction du graphe routier.
"""

from __future__ import annotations

import argparse
import runpy
import sys
import time
from pathlib import Path

RACINE = Path(__file__).resolve().parent
sys.path.insert(0, str(RACINE / "src"))

ETAPES = {
    0: ("Téléchargement des sources", "src/telecharger_donnees.py"),
    1: ("Préparation des couches", "src/p01_preparer_couches.py"),
    2: ("Construction du graphe routier", "src/p02_construire_graphe.py"),
    3: ("Accessibilité de référence", "src/p03_accessibilite_reference.py"),
    4: ("Scénarios de blocage", "src/p04_scenarios_blocage.py"),
    5: ("Cartes et graphiques", "src/p05_cartes.py"),
}


def executer(numero: int) -> None:
    libelle, script = ETAPES[numero]
    print("\n" + "=" * 78)
    print(f"ÉTAPE {numero} — {libelle}")
    print("=" * 78, flush=True)
    debut = time.perf_counter()
    sys.argv = [script]
    runpy.run_path(str(RACINE / script), run_name="__main__")
    print(f"[étape {numero} terminée en {time.perf_counter() - debut:.0f} s]")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--depuis", type=int, default=0, help="première étape à exécuter")
    p.add_argument("--etape", type=int, help="n'exécuter que cette étape")
    args = p.parse_args()

    numeros = [args.etape] if args.etape is not None else [
        n for n in sorted(ETAPES) if n >= args.depuis
    ]
    debut = time.perf_counter()
    for n in numeros:
        executer(n)
    print(f"\nChaîne terminée en {(time.perf_counter() - debut) / 60:.1f} minutes.")


if __name__ == "__main__":
    main()
