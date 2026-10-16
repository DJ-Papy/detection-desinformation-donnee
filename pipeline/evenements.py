"""
RECONSTRUCTION DES ÉVÉNEMENTS INTER-MÉDIAS (module 5, unité d'analyse)
=======================================================================

Mémoire, §2.6 : « Les événements sont reconstruits en regroupant les articles
par indicateur dominant et par semaine de publication, en ne retenant que les
regroupements couverts par au moins trois médias distincts. » Sur le corpus du
mémoire, cette procédure produit 27 événements.

Définitions opérationnelles retenues ici (le code d'origine n'a pas été
conservé ; ces définitions sont celles qui découlent du texte et elles sont
paramétrables pour l'analyse de sensibilité) :

  - INDICATEUR DOMINANT d'un article : l'indicateur (module 2) le plus
    fréquent parmi ses claims, en ignorant « inconnu ». Égalité départagée
    par l'ordre du lexique du module 2 (chômage, PIB, inflation, dette,
    population, salaire). Un article sans claim rattaché n'a pas
    d'indicateur dominant et n'entre dans aucun événement.
  - SEMAINE : semaine ISO 8601 de la date de publication (lundi → dimanche).
  - SEUIL : au moins `min_medias` médias DISTINCTS (3 par défaut). Plusieurs
    articles d'un même média sont conservés dans l'événement.

⚠️ Limite reconnue par le mémoire : ce découpage dépend de ses paramètres
(indicateur dominant, fenêtre hebdomadaire, seuil de trois médias) ; un
article publié le dimanche et sa reprise du lundi tombent dans deux semaines
différentes. Voir docs/limites_connues.md.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date
from typing import Dict, Iterable, List, Optional, Sequence

from module2_structuration import Module2Structuration

ORDRE_INDICATEURS: Sequence[str] = tuple(Module2Structuration.INDICATEURS_KEYWORDS)


@dataclass
class Evenement:
    """Un événement : un indicateur couvert par plusieurs médias la même semaine."""
    cle: str                       # "chômage 2023-W46"
    indicateur: str
    semaine: str                   # "2023-W46"
    article_ids: List[str] = field(default_factory=list)
    medias: List[str] = field(default_factory=list)   # médias distincts, triés

    @property
    def n_medias(self) -> int:
        return len(self.medias)


def indicateur_dominant(indicateurs: Iterable[str]) -> str:
    """Indicateur le plus fréquent (hors « inconnu ») ; "" s'il n'y en a aucun."""
    compte = Counter(i for i in indicateurs if i and i != "inconnu")
    if not compte:
        return ""
    meilleur = max(compte.values())
    for indic in ORDRE_INDICATEURS:
        if compte.get(indic) == meilleur:
            return indic
    # indicateur hors lexique (ne devrait pas arriver) : ordre alphabétique
    return sorted(i for i, n in compte.items() if n == meilleur)[0]


def semaine_iso(date_iso: str) -> Optional[str]:
    """'2023-11-15' → '2023-W46' ; None si la date est absente ou invalide."""
    try:
        annee, semaine, _ = date.fromisoformat(date_iso[:10]).isocalendar()
    except (ValueError, TypeError):
        return None
    return f"{annee}-W{semaine:02d}"


def reconstruire_evenements(
    articles: Sequence[Dict[str, str]],
    min_medias: int = 3,
) -> List[Evenement]:
    """
    Regroupe les articles en événements.

    Args:
        articles: dicts avec au moins `id`, `media`, `date` et
            `indicateur_dominant` (calculé par `indicateur_dominant`).
        min_medias: nombre minimal de médias distincts pour retenir un groupe.

    Returns:
        Événements retenus, triés par semaine puis indicateur.
    """
    groupes: Dict[tuple, List[Dict[str, str]]] = defaultdict(list)
    for art in articles:
        indic = art.get("indicateur_dominant", "")
        semaine = semaine_iso(art.get("date", ""))
        if not indic or not semaine:
            continue
        groupes[(indic, semaine)].append(art)

    evenements = []
    for (indic, semaine), arts in groupes.items():
        medias = sorted({a["media"] for a in arts})
        if len(medias) < min_medias:
            continue
        evenements.append(Evenement(
            cle=f"{indic} {semaine}",
            indicateur=indic,
            semaine=semaine,
            article_ids=[a["id"] for a in arts],
            medias=medias,
        ))
    evenements.sort(key=lambda e: (e.semaine, ORDRE_INDICATEURS.index(e.indicateur)
                                   if e.indicateur in ORDRE_INDICATEURS else 99))
    return evenements
