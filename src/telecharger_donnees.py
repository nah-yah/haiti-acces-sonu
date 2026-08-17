"""
Téléchargement des sources externes du projet.

Idempotent : un fichier déjà présent et non vide n'est pas retéléchargé. Chaque
source porte son URL stable et sa page de catalogue.

    python src/telecharger_donnees.py
    python src/telecharger_donnees.py --forcer
"""

from __future__ import annotations

import argparse
import sys
import zipfile

import requests

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent))

from config import DATA_BRUT  # noqa: E402
from utils import log  # noqa: E402

ENTETES = {"User-Agent": "SCI-analyse-acces-SONU/1.0 (recherche appliquee)"}

SOURCES = [
    {
        "nom": "Réseau routier OpenStreetMap, Haïti",
        "fichier": "hotosm_hti_roads_gpkg.zip",
        "url": (
            "https://production-raw-data-api.s3.amazonaws.com/ISO3/HTI/roads/"
            "hotosm_hti_roads_osm_gpkg.zip"
        ),
        "catalogue": "https://data.humdata.org/dataset/hotosm_hti_roads",
        "licence": "Open Database License (ODbL), contributeurs OpenStreetMap",
    },
    {
        "nom": "Population maillée 100 m, Haïti 2020 (contrainte, ajustée ONU)",
        "fichier": "hti_ppp_2020_UNadj_constrained.tif",
        "url": (
            "https://data.worldpop.org/GIS/Population/Global_2000_2020_Constrained/"
            "2020/BSGM/HTI/hti_ppp_2020_UNadj_constrained.tif"
        ),
        "catalogue": "https://hub.worldpop.org/geodata/summary?id=39527",
        "licence": "Creative Commons Attribution 4.0",
    },
]

# Sources reprises du projet QGIS « geospatial-ssr-haiti-2024 » du même auteur :
# mêmes découpages administratifs et même millésime de population.
SOURCES_REPRISES = {
    "hti_admin_boundaries/": "OCHA COD-AB Haïti, https://data.humdata.org/dataset/cod-ab-hti",
    "hti_health_facilities/": "HOT OSM Haïti, https://data.humdata.org/dataset/hotosm_hti_health_facilities",
    "hti_admpop_adm2_2024.csv": "OCHA COD-PS Haïti, https://data.humdata.org/dataset/cod-ps-hti",
    "acled_civilian_targeting_adm2.xlsx": "ACLED via HDX, https://data.humdata.org/dataset/haiti-acled-conflict-data",
}


def telecharger(source: dict, forcer: bool = False) -> None:
    cible = DATA_BRUT / source["fichier"]
    if cible.exists() and cible.stat().st_size > 0 and not forcer:
        log(f"déjà présent : {source['fichier']} ({cible.stat().st_size / 1e6:.1f} Mo)")
        return

    log(f"téléchargement : {source['nom']}")
    cible.parent.mkdir(parents=True, exist_ok=True)
    with requests.get(source["url"], headers=ENTETES, stream=True, timeout=180) as r:
        r.raise_for_status()
        with open(cible, "wb") as f:
            for bloc in r.iter_content(chunk_size=1 << 20):
                f.write(bloc)
    log(f"   écrit : {cible.name} ({cible.stat().st_size / 1e6:.1f} Mo)")


def extraire_routes() -> None:
    """Déballe roads.gpkg, le format lu par la suite du pipeline."""
    archive = DATA_BRUT / "hotosm_hti_roads_gpkg.zip"
    cible = DATA_BRUT / "roads.gpkg"
    if cible.exists() and cible.stat().st_size > 0:
        log(f"déjà extrait : roads.gpkg ({cible.stat().st_size / 1e6:.1f} Mo)")
        return
    if not archive.exists():
        log("archive des routes absente, extraction impossible")
        return
    with zipfile.ZipFile(archive) as z:
        with z.open("roads.gpkg") as src, open(cible, "wb") as dst:
            while bloc := src.read(1 << 20):
                dst.write(bloc)
    log(f"   extrait : roads.gpkg ({cible.stat().st_size / 1e6:.1f} Mo)")


def main() -> None:
    parseur = argparse.ArgumentParser(description=__doc__)
    parseur.add_argument("--forcer", action="store_true", help="retélécharge même si présent")
    args = parseur.parse_args()

    for source in SOURCES:
        telecharger(source, forcer=args.forcer)
    extraire_routes()

    manquants = [f for f in SOURCES_REPRISES if not (DATA_BRUT / f.rstrip("/")).exists()]
    if manquants:
        log("")
        log("Fichiers attendus mais absents (à copier depuis le projet SSR 2024) :")
        for f in manquants:
            log(f"   {f}  <-  {SOURCES_REPRISES[f]}")


if __name__ == "__main__":
    main()
