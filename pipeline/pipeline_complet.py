"""
PIPELINE COMPLET — Orchestrateur
=================================

Mémoire INSEEC MSc — Data & Marketing Digital — 2025-2026

Assemble toute la chaîne de détection sur un ÉVÉNEMENT (un fait chiffré
couvert par plusieurs médias) :

  M0  Parser           → (déjà fait : corpus CSV)
  M1  Extraction       → claims chiffrés de chaque article
  M2  Structuration    → indicateur, valeur, période, unité
  M1.5 Classifieur     → régime 1 (vérifiable) ou régime 2 (cadrage)
        │
        ├── RÉGIME 1 → M3 (valeur INSEE) → M4 (verdict de véracité)
        └── RÉGIME 2 → agrégé pour M5 (analyse de cadrage inter-médias)

Le pipeline produit donc DEUX sorties complémentaires, conformes aux deux
niveaux d'analyse du mémoire :
  - un tableau de FACT-CHECKING (régime 1) : claims vérifiés vs INSEE
  - une analyse de CADRAGE (régime 2) : comment les médias sélectionnent
    et cadrent les chiffres non vérifiables du même événement

Mode INSEE : 'mock' (sans réseau) ou 'production' (API réelle).

USAGE (depuis la racine du dépôt)
    python pipeline/pipeline_complet.py                       # démo, corpus fictif
    python pipeline/pipeline_complet.py mon_corpus.csv \
        --evenement "chômage T3 2023" --debut 2023-11-14 --fin 2023-11-18 \
        --indicateur chômage --periode 2023-Q3 \
        --mots-cles chômage chomage emploi BIT [--production]

v2 : la date de l'article est transmise au classifieur (exclusion « année
future ») ; le corpus est lu par `corpus_io.charger_corpus` (séparateur
détecté automatiquement) au lieu d'un fichier « corpus_brut.csv » codé en dur.

Auteur : Florian, mai 2026 (v2 reconstruite en octobre 2026).
"""

from __future__ import annotations
import argparse
import csv
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Dict, Optional

logging.disable(logging.INFO)
csv.field_size_limit(10000000)

from corpus_io import charger_corpus

from module1_extraction import Module1Extraction
from module2_structuration import Module2Structuration, ClaimCandidat as CC2
from module1_5_classifieur_regime import ClassifieurRegime, Regime
from module3_matching_insee import Module3MatchingINSEE
from module4_validation_revise import (
    Module4Validation, ClaimAValider, DonneeOfficielle as DO4)
from module5_cadrage import Module5Cadrage, ArticleCadrage


# Plages plausibles par indicateur (filtre de qualification du fact-check).
# Larges à dessein : on ne veut pas exclure une vraie erreur grave, seulement
# les confusions de grandeur évidentes (ex : taux d'emploi des seniors 60,5 %
# comparé au taux de chômage).
PLAGES_PLAUSIBLES = {
    "chômage": (2.0, 15.0),     # taux de chômage BIT plausible
    "inflation": (-2.0, 20.0),  # glissement annuel des prix
    "PIB": (-5.0, 5.0),         # variation trimestrielle en volume
    "dette": (50.0, 150.0),     # % du PIB
}


def valeur_plausible(indicateur: str, valeur: float) -> bool:
    """Vrai si la valeur est dans la plage plausible de l'indicateur."""
    if indicateur not in PLAGES_PLAUSIBLES:
        return True  # pas de contrainte connue → on laisse passer
    lo, hi = PLAGES_PLAUSIBLES[indicateur]
    return lo <= valeur <= hi


@dataclass
class ResultatEvenement:
    """Résultat complet du pipeline sur un événement."""
    evenement: str
    n_articles: int
    factcheck: List[Dict] = field(default_factory=list)   # claims régime 1 vérifiés
    analyse_cadrage: Optional[object] = None              # AnalyseCadrage (M5)


class PipelineComplet:
    """Orchestre M1 → M2 → M1.5 → (M3+M4 | M5) sur un événement."""

    def __init__(self, mode_insee: str = "mock", cache_path: str = "cache_insee.db"):
        self.m1 = Module1Extraction()
        self.m2 = Module2Structuration()
        self.clf = ClassifieurRegime()
        self.m3 = Module3MatchingINSEE(mode=mode_insee, cache_path=cache_path)
        self.m4 = Module4Validation()
        self.m5 = Module5Cadrage()

    def _plausible(self, indicateur: str, valeur: float) -> bool:
        """
        Vérifie qu'une valeur est dans la plage plausible de l'indicateur.
        Élimine les pourcentages qui ne sont manifestement pas le taux visé
        (ex : taux d'emploi des seniors 60,5% comparé au taux de chômage).
        Les plages sont larges (on ne veut pas exclure une vraie erreur grave,
        juste les confusions de grandeur évidentes) : voir PLAGES_PLAUSIBLES.
        """
        return valeur_plausible(indicateur, valeur)

    def traiter_evenement(
        self, evenement: str, articles: List[Dict],
        indicateur_attendu: str, periode_insee: str,
        mots_cles: List[str]
    ) -> ResultatEvenement:
        """
        Args:
            evenement: libellé (ex: "chômage T3 2023")
            articles: liste de dicts {id, media, titre, texte, date}
            indicateur_attendu: indicateur INSEE de référence (ex: "chômage")
            periode_insee: période à vérifier (ex: "2023-Q3")
            mots_cles: pour le filtre de pertinence M5
        """
        factcheck = []
        articles_cadrage = []

        for art in articles:
            # M1 + M2 : extraire et structurer les claims
            claims = self.m1.extraire(art["texte"], art["id"])
            cands = [CC2(c.claim_id, c.phrase, c.valeur_brute) for c in claims]
            structs = self.m2.structurer(cands, art["date"])

            chiffres_bruts = []
            for s in structs:
                # Reconstituer une valeur brute lisible (M2 ne la conserve pas)
                valeur_brute = f"{s.valeur}{s.unite}".strip()
                chiffres_bruts.append(valeur_brute)

                # M1.5 : classer le régime
                reg = self.clf.classer(
                    s.claim_id, s.phrase_originale,
                    s.indicateur, s.unite, s.est_variation, s.modificateur,
                    date_article=art["date"])

                # ── FILTRE DE QUALIFICATION avant fact-check ──────────────
                # Un claim n'est fact-checkable (régime 1) que s'il est :
                #   (a) en régime de vérifiabilité forte (pas une prévision)
                #   (b) sur l'indicateur de référence de l'événement
                #   (c) exprimé en % (un taux, pas un effectif/volume)
                #   (d) dans une plage plausible pour cet indicateur
                #   (e) pas une variation ("+0,2 point") mais un niveau
                est_factcheckable = (
                    reg.regime == Regime.FORTE
                    and s.indicateur == indicateur_attendu
                    and s.unite == "%"
                    and not s.est_variation
                    and self._plausible(s.indicateur, s.valeur)
                )

                if est_factcheckable:
                    # RÉGIME 1 → M3 + M4 (fact-check)
                    donnee = self.m3.matcher(
                        s.claim_id, s.indicateur, periode_insee,
                        phrase=s.phrase_originale)
                    if donnee.trouve:
                        claim4 = ClaimAValider(
                            s.claim_id, s.valeur, valeur_brute,
                            s.indicateur, s.unite,
                            phrase_originale=s.phrase_originale,
                            modificateur=s.modificateur)
                        do4 = DO4(s.indicateur, donnee.valeur, periode_insee,
                                  donnee.unite, libelle=donnee.libelle)
                        res = self.m4.valider(claim4, do4)
                        factcheck.append({
                            "media": art["media"],
                            "claim": f"{s.valeur}{s.unite}",
                            "phrase": s.phrase_originale[:80],
                            "insee": donnee.valeur,
                            "verdict": res.verdict.value,
                            "ecart": res.ecart_absolu,
                        })

            # Préparer l'article pour M5 (cadrage régime 2)
            articles_cadrage.append(ArticleCadrage(
                art["id"], art["media"], art["titre"], art["texte"], art["date"],
                [c.valeur_brute for c in claims]))

        # M5 : analyse de cadrage sur l'ensemble
        analyse = self.m5.analyser_evenement(
            evenement, articles_cadrage, mots_cles_evenement=mots_cles)

        return ResultatEvenement(
            evenement=evenement,
            n_articles=len(articles),
            factcheck=factcheck,
            analyse_cadrage=analyse,
        )

    def fermer(self):
        self.m3.fermer()


# ============================================================================
# DÉMO / LIGNE DE COMMANDE
# ============================================================================

RACINE_DEPOT = Path(__file__).resolve().parent.parent
CORPUS_EXEMPLE = RACINE_DEPOT / "data" / "exemple" / "corpus_exemple.csv"


def afficher(res: ResultatEvenement) -> None:
    """Affiche les deux sorties du pipeline pour un événement."""
    print("=" * 68)
    print(f"PIPELINE COMPLET — {res.evenement}")
    print("=" * 68)
    print(f"Articles traités : {res.n_articles}")

    print(f"\n{'─'*68}")
    print("NIVEAU 1 — FACT-CHECKING (régime 1, vérifiable vs INSEE)")
    print(f"{'─'*68}")
    if res.factcheck:
        for fc in res.factcheck:
            print(f"  [{fc['media'][:18]:18s}] claim {fc['claim']:8s} vs INSEE "
                  f"{fc['insee']}% → {fc['verdict'].upper()} (écart {fc['ecart']})")
            print(f"       « {fc['phrase']}... »")
    else:
        print("  Aucun claim régime 1 sur l'indicateur de référence.")

    print(f"\n{'─'*68}")
    print("NIVEAU 2 — CADRAGE (régime 2, analyse inter-médias)")
    print(f"{'─'*68}")
    a = res.analyse_cadrage
    if a:
        print(f"  Articles pertinents : {a.n_pertinents}/{a.n_articles}")
        print(f"  Indice de divergence des sélections : {a.indice_divergence}")
        print(f"  Chiffres consensuels : {', '.join(a.chiffres_consensuels) or '(aucun)'}")
        print(f"\n  Signature par média :")
        for s in a.signatures:
            print(f"    [{s.media[:18]:18s}] couverture {s.taux_couverture:.0%}, "
                  f"cadrage={s.fonction_dominante or 'n/a'}, "
                  f"exclusifs={len(s.chiffres_exclusifs)}")


def main(argv: Optional[List[str]] = None) -> ResultatEvenement:
    p = argparse.ArgumentParser(
        description="Pipeline complet (M1 → M5) sur un événement d'un corpus CSV.")
    p.add_argument("corpus", nargs="?", default=str(CORPUS_EXEMPLE),
                   help="CSV id;media;date;titre;texte (défaut : corpus fictif d'exemple)")
    p.add_argument("--evenement", default="chômage T3 2023")
    p.add_argument("--debut", default="2023-11-14", help="date min (AAAA-MM-JJ)")
    p.add_argument("--fin", default="2023-11-18", help="date max (AAAA-MM-JJ)")
    p.add_argument("--indicateur", default="chômage",
                   help="indicateur de référence : chômage, inflation, PIB, dette")
    p.add_argument("--periode", default="2023-Q3",
                   help="période INSEE à vérifier : 2023-Q3, 2023-07…")
    p.add_argument("--mots-cles", nargs="+",
                   default=["chômage", "chomage", "emploi", "BIT"],
                   help="filtre de pertinence du module 5")
    p.add_argument("--production", action="store_true",
                   help="interroger réellement l'API INSEE (Internet requis)")
    args = p.parse_args(argv)

    articles = charger_corpus(args.corpus)
    cibles = [a for a in articles if args.debut <= a["date"] <= args.fin]

    pipeline = PipelineComplet(
        mode_insee="production" if args.production else "mock",
        cache_path="cache_insee.db" if args.production else ":memory:")
    try:
        res = pipeline.traiter_evenement(
            evenement=args.evenement,
            articles=cibles,
            indicateur_attendu=args.indicateur,
            periode_insee=args.periode,
            mots_cles=args.mots_cles,
        )
    finally:
        pipeline.fermer()
    afficher(res)
    return res


if __name__ == "__main__":
    main()
