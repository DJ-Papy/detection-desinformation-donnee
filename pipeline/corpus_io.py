"""
CORPUS I/O — lecture du corpus CSV commun à tous les scripts
=============================================================

Un seul format d'entrée pour `pipeline_complet.py` et `analyse_corpus.py` :
un CSV UTF-8 avec au minimum les colonnes

    id ; media ; date ; titre ; texte

- `date` au format ISO AAAA-MM-JJ ;
- séparateur détecté automatiquement sur la ligne d'en-tête parmi
  « ; » (sortie de `module0_parser_europresse.py` / `outil_corpus_stats.py`),
  « | » (format de travail utilisé pendant le mémoire), « , » et tabulation ;
- les textes peuvent contenir des retours à la ligne s'ils sont entre
  guillemets (c'est le cas des exports du module 0).

Les doublons d'identifiant sont écartés (première occurrence conservée) et
signalés : la déduplication « raisonnée » (meilleur taux d'extraction) se fait
en amont, dans `outil_corpus_stats.py`, qui a accès aux PDF.
"""

from __future__ import annotations

import csv
import logging
from pathlib import Path
from typing import Dict, List

logger = logging.getLogger("CorpusIO")

COLONNES_REQUISES = ("id", "media", "date", "titre", "texte")
SEPARATEURS_POSSIBLES = (";", "|", ",", "\t")


def _detecter_separateur(ligne_entete: str) -> str:
    """Choisit le séparateur le plus fréquent de la ligne d'en-tête."""
    comptes = {sep: ligne_entete.count(sep) for sep in SEPARATEURS_POSSIBLES}
    sep, n = max(comptes.items(), key=lambda kv: kv[1])
    if n == 0:
        raise ValueError(
            "Impossible de détecter le séparateur du CSV : la ligne d'en-tête "
            f"ne contient aucun de {SEPARATEURS_POSSIBLES!r}.")
    return sep


def charger_corpus(chemin: str | Path) -> List[Dict[str, str]]:
    """
    Charge un corpus d'articles depuis un CSV.

    Returns:
        Liste de dicts {id, media, date, titre, texte, ...} (colonnes
        supplémentaires conservées), dans l'ordre du fichier, sans doublon.
    """
    chemin = Path(chemin)
    if not chemin.exists():
        raise FileNotFoundError(f"Corpus introuvable : {chemin}")

    csv.field_size_limit(10**8)
    with open(chemin, encoding="utf-8-sig", newline="") as f:
        sep = _detecter_separateur(f.readline())
        f.seek(0)
        lecteur = csv.DictReader(f, delimiter=sep)
        manquantes = [c for c in COLONNES_REQUISES
                      if c not in (lecteur.fieldnames or [])]
        if manquantes:
            raise ValueError(
                f"Colonnes manquantes dans {chemin.name} : {manquantes}. "
                f"Colonnes attendues : {list(COLONNES_REQUISES)}.")

        articles: List[Dict[str, str]] = []
        vus = set()
        doublons = 0
        for ligne in lecteur:
            if ligne["id"] in vus:
                doublons += 1
                continue
            vus.add(ligne["id"])
            articles.append({k: (v or "") for k, v in ligne.items()})

    if doublons:
        logger.warning(f"{doublons} doublon(s) d'identifiant ignoré(s) dans {chemin.name}.")
    return articles
