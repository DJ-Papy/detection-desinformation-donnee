"""
OUTIL CORPUS : Dédoublonnage + Statistiques
============================================

Mémoire INSEEC MSc — Data & Marketing Digital — 2025-2026

Cet outil prend un dossier de PDF Europresse, parse tous les articles,
les déduplique par identifiant Europresse natif, puis produit le portrait
statistique du corpus réel :

  1. Volume RÉEL d'articles uniques (vs comptage brut avec doublons)
  2. Distribution par média
  3. Distribution temporelle (par mois/trimestre)
  4. Couverture des événements INSEE (rapproche les dates des publications)
  5. Profil de vérifiabilité (% régime 1 fact-checkable vs régime 2 cadrage)
  6. Articles couvrant le même événement (pour l'analyse inter-médias)

POURQUOI CET OUTIL
    Le suivi de collecte (Cowork) comptabilise un article dans plusieurs
    thématiques → surcomptage. Le dédoublonnage par ID Europresse
    (champ news·YYYYMMDD·SOURCE·hash, unique par article) donne le
    volume réel et reproductible, traçable pour la charte IA.

USAGE
    python outil_corpus_stats.py /chemin/vers/dossier_pdf [rapport.json]

    ou en Python :
        from outil_corpus_stats import AnalyseurCorpus
        analyseur = AnalyseurCorpus()
        analyseur.charger_dossier("/chemin/dossier")
        analyseur.rapport()

Auteur : Florian, mai 2026.
"""

from __future__ import annotations
import os
import sys
import json
import logging
from pathlib import Path
from dataclasses import dataclass, field, asdict
from collections import Counter, defaultdict
from typing import List, Dict, Optional, Tuple

from module0_parser_europresse import EuropresseParser, ArticleEuropresse
from module1_extraction import Module1Extraction
from module2_structuration import Module2Structuration, ClaimCandidat as CC2
from module1_5_classifieur_regime import ClassifieurRegime, Regime

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s")
logger = logging.getLogger("Corpus")


# ============================================================================
# CALENDRIER DES ÉVÉNEMENTS INSEE (rappel de la grille)
# ============================================================================
# Format : (indicateur, date_publication_iso, periode, valeur)
# Sert à rattacher chaque article à l'événement INSEE qu'il couvre
# potentiellement (fenêtre de 0 à 4 jours après publication).

EVENEMENTS_INSEE = [
    # Inflation mensuelle (date provisoire INSEE)
    ("inflation", "2023-03-31", "2023-03", 5.6),
    ("inflation", "2023-06-30", "2023-06", 4.5),
    ("inflation", "2023-07-28", "2023-07", 4.3),
    ("inflation", "2023-08-31", "2023-08", 4.8),
    ("inflation", "2023-09-29", "2023-09", 4.9),
    ("inflation", "2024-08-30", "2024-08", 1.9),
    # Chômage trimestriel
    ("chômage", "2023-05-16", "2023-Q1", 7.1),
    ("chômage", "2023-08-11", "2023-Q2", 7.2),
    ("chômage", "2023-11-15", "2023-Q3", 7.4),
    ("chômage", "2024-02-13", "2023-Q4", 7.5),
    ("chômage", "2024-05-17", "2024-Q1", 7.5),
    ("chômage", "2024-08-09", "2024-Q2", 7.3),
    # PIB
    ("PIB", "2024-01-30", "2023-Q4", 0.1),
    ("PIB", "2024-08-30", "2024-Q2", 0.2),
    # Dette / déficit (publication 26 mars 2024 = déficit 2023)
    ("déficit", "2024-03-26", "2023", 5.5),
    ("dette", "2023-09-29", "2023-Q2", 111.8),
]


# ============================================================================
# STRUCTURES
# ============================================================================

@dataclass
class StatsArticle:
    """Métadonnées + diagnostics d'un article unique pour les stats."""
    article_id: str
    source_media: str
    date_publication: str
    titre: str
    mots: int
    source_pdf: str
    nb_claims: int = 0
    nb_regime1: int = 0       # claims fact-checkables (vérifiabilité forte)
    nb_regime2: int = 0       # claims de cadrage (vérifiabilité faible)
    nb_indetermine: int = 0
    evenement_insee: str = "" # événement rattaché, si proche d'une publi INSEE

    @property
    def profil(self) -> str:
        """Profil dominant de l'article."""
        if self.nb_claims == 0:
            return "sans_claim"
        if self.nb_regime1 > self.nb_regime2:
            return "fact_checkable"
        elif self.nb_regime2 > self.nb_regime1:
            return "cadrage"
        return "mixte"


# ============================================================================
# ANALYSEUR DE CORPUS
# ============================================================================

class AnalyseurCorpus:
    """Charge, déduplique et analyse statistiquement un corpus Europresse."""

    def __init__(self):
        self.parser = EuropresseParser()
        self.m1 = Module1Extraction()
        self.m2 = Module2Structuration()
        self.clf = ClassifieurRegime()

        # Stockage : ID → ArticleEuropresse (déduplication automatique)
        self.articles_uniques: Dict[str, ArticleEuropresse] = {}
        # ID → liste des PDF où l'article apparaît (pour tracer les doublons)
        self.occurrences: Dict[str, List[str]] = defaultdict(list)
        self.stats: Dict[str, StatsArticle] = {}
        self.nb_articles_bruts = 0

    # ---- Chargement ----

    def charger_dossier(self, chemin_dossier: str) -> None:
        """Parse tous les PDF d'un dossier et déduplique par ID."""
        dossier = Path(chemin_dossier)
        pdfs = sorted(dossier.glob("*.pdf"))
        logger.info(f"{len(pdfs)} PDF trouvé(s) dans {dossier}")
        for pdf in pdfs:
            self._charger_pdf(str(pdf))

    def charger_pdfs(self, chemins: List[str]) -> None:
        """Parse une liste explicite de PDF."""
        for c in chemins:
            self._charger_pdf(c)

    def _charger_pdf(self, chemin_pdf: str) -> None:
        nom = Path(chemin_pdf).name
        try:
            articles = self.parser.parser(chemin_pdf)
        except Exception as e:
            logger.error(f"Échec parsing {nom} : {e}")
            return

        for art in articles:
            self.nb_articles_bruts += 1
            self.occurrences[art.article_id].append(nom)
            # Déduplication : on garde la première occurrence
            if art.article_id not in self.articles_uniques:
                self.articles_uniques[art.article_id] = art

    # ---- Analyse ----

    def analyser(self) -> None:
        """Calcule les statistiques sur chaque article unique."""
        for aid, art in self.articles_uniques.items():
            claims = self.m1.extraire(art.texte, aid)
            cands = [CC2(c.claim_id, c.phrase, c.valeur_brute) for c in claims]
            structs = self.m2.structurer(cands, art.date_publication)

            n1 = n2 = nind = 0
            for s in structs:
                res = self.clf.classer(
                    s.claim_id, s.phrase_originale,
                    s.indicateur, s.unite, s.est_variation, s.modificateur
                )
                if res.regime == Regime.FORTE:
                    n1 += 1
                elif res.regime == Regime.FAIBLE:
                    n2 += 1
                else:
                    nind += 1

            evt = self._rattacher_evenement(art)

            self.stats[aid] = StatsArticle(
                article_id=aid,
                source_media=art.source_media,
                date_publication=art.date_publication,
                titre=art.titre,
                mots=art.mots_extraits,
                source_pdf=art.source_pdf,
                nb_claims=len(structs),
                nb_regime1=n1,
                nb_regime2=n2,
                nb_indetermine=nind,
                evenement_insee=evt,
            )

    def _rattacher_evenement(self, art: ArticleEuropresse) -> str:
        """
        Rattache un article à un événement INSEE si sa date de publication
        tombe dans les 0-4 jours après une publication INSEE.
        """
        if not art.date_publication:
            return ""
        from datetime import datetime, timedelta
        try:
            d_art = datetime.fromisoformat(art.date_publication)
        except ValueError:
            return ""

        for indic, date_insee, periode, _ in EVENEMENTS_INSEE:
            try:
                d_insee = datetime.fromisoformat(date_insee)
            except ValueError:
                continue
            delta = (d_art - d_insee).days
            if 0 <= delta <= 4:
                return f"{indic} {periode} (publi {date_insee})"
        return ""

    # ---- Rapport ----

    def rapport(self) -> str:
        """Génère le rapport statistique textuel."""
        if not self.stats:
            self.analyser()

        n_uniques = len(self.articles_uniques)
        lignes = []
        lignes.append("=" * 70)
        lignes.append("PORTRAIT STATISTIQUE DU CORPUS")
        lignes.append("=" * 70)

        # 1. Volume réel vs brut
        doublons = sum(1 for occ in self.occurrences.values() if len(occ) > 1)
        lignes.append(f"\n1. VOLUME")
        lignes.append(f"   Articles parsés (bruts, avec répétitions PDF) : {self.nb_articles_bruts}")
        lignes.append(f"   Articles UNIQUES (dédupliqués par ID)         : {n_uniques}")
        lignes.append(f"   Articles apparaissant dans plusieurs PDF      : {doublons}")

        # 2. Distribution par média
        par_media = Counter(s.source_media for s in self.stats.values())
        lignes.append(f"\n2. DISTRIBUTION PAR MÉDIA")
        for media, n in par_media.most_common():
            lignes.append(f"   {media:30s} : {n:>4} article(s)")

        # 3. Distribution temporelle
        par_annee = Counter(s.date_publication[:7] for s in self.stats.values()
                            if s.date_publication)
        lignes.append(f"\n3. DISTRIBUTION TEMPORELLE (par mois)")
        for mois in sorted(par_annee.keys()):
            n = par_annee[mois]
            lignes.append(f"   {mois} : {n:>3} {'▪' * n}")

        # 4. Profil de vérifiabilité
        total_claims = sum(s.nb_claims for s in self.stats.values())
        total_r1 = sum(s.nb_regime1 for s in self.stats.values())
        total_r2 = sum(s.nb_regime2 for s in self.stats.values())
        total_ind = sum(s.nb_indetermine for s in self.stats.values())
        lignes.append(f"\n4. PROFIL DE VÉRIFIABILITÉ DES CLAIMS")
        lignes.append(f"   Total claims chiffrés extraits : {total_claims}")
        if total_claims:
            lignes.append(f"   Régime 1 (fact-checkable INSEE) : {total_r1:>4} ({100*total_r1//total_claims}%)")
            lignes.append(f"   Régime 2 (cadrage/framing)      : {total_r2:>4} ({100*total_r2//total_claims}%)")
            lignes.append(f"   Indéterminé                     : {total_ind:>4} ({100*total_ind//total_claims}%)")

        # 5. Profil des articles
        par_profil = Counter(s.profil for s in self.stats.values())
        lignes.append(f"\n5. PROFIL DES ARTICLES")
        libelles = {
            "fact_checkable": "Dominante fact-checkable (régime 1)",
            "cadrage": "Dominante cadrage (régime 2)",
            "mixte": "Mixte",
            "sans_claim": "Sans claim chiffré",
        }
        for profil, n in par_profil.most_common():
            lignes.append(f"   {libelles.get(profil, profil):40s} : {n:>4} article(s)")

        # 6. Couverture des événements INSEE
        evts = defaultdict(list)
        for s in self.stats.values():
            if s.evenement_insee:
                evts[s.evenement_insee].append(s.source_media)
        lignes.append(f"\n6. COUVERTURE DES ÉVÉNEMENTS INSEE")
        if evts:
            lignes.append(f"   {len(evts)} événement(s) INSEE couvert(s) :")
            for evt, medias in sorted(evts.items()):
                n_medias = len(set(medias))
                marqueur = "🎯" if n_medias >= 3 else "  "
                lignes.append(f"   {marqueur} {evt:35s} : {n_medias} média(s) — {', '.join(sorted(set(medias)))}")
            # Compter les événements exploitables pour l'analyse inter-médias
            exploitables = sum(1 for m in evts.values() if len(set(m)) >= 3)
            lignes.append(f"\n   → {exploitables} événement(s) avec ≥3 médias (analyse inter-médias possible)")
        else:
            lignes.append("   Aucun article rattaché à un événement INSEE de la grille.")
            lignes.append("   (normal si le corpus ne couvre pas ces dates précises)")

        # 7. Synthèse exploitabilité
        n_factcheck = par_profil.get("fact_checkable", 0) + par_profil.get("mixte", 0)
        lignes.append(f"\n7. SYNTHÈSE D'EXPLOITABILITÉ")
        lignes.append(f"   Articles à dominante fact-checkable ou mixte : {n_factcheck}/{n_uniques}")
        lignes.append(f"   → Périmètre du fact-checking numérique (régime 1)")
        lignes.append(f"   Articles à dominante cadrage : {par_profil.get('cadrage', 0)}/{n_uniques}")
        lignes.append(f"   → Périmètre de l'analyse de framing (régime 2)")

        return "\n".join(lignes)

    def exporter_json(self, chemin: str) -> None:
        """Exporte les stats détaillées en JSON."""
        if not self.stats:
            self.analyser()
        data = {
            "nb_articles_bruts": self.nb_articles_bruts,
            "nb_articles_uniques": len(self.articles_uniques),
            "articles": [asdict(s) for s in self.stats.values()],
            "doublons": {aid: occ for aid, occ in self.occurrences.items()
                         if len(occ) > 1},
        }
        with open(chemin, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        logger.info(f"Stats exportées : {chemin}")

    def exporter_csv_corpus(self, chemin: str) -> None:
        """Exporte le corpus dédupliqué au format CSV pour le pipeline."""
        import csv
        if not self.stats:
            self.analyser()
        with open(chemin, "w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f, delimiter=";", quoting=csv.QUOTE_ALL)
            writer.writerow(["id", "media", "date", "titre", "texte",
                             "evenement_insee", "profil", "nb_claims"])
            for aid, art in self.articles_uniques.items():
                s = self.stats[aid]
                writer.writerow([
                    aid, art.source_media, art.date_publication, art.titre,
                    art.texte, s.evenement_insee, s.profil, s.nb_claims,
                ])
        logger.info(f"Corpus dédupliqué exporté : {chemin}")


# ============================================================================
# POINT D'ENTRÉE
# ============================================================================

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage : python outil_corpus_stats.py <dossier_pdf|pdf1 pdf2...> [rapport.json]")
        sys.exit(1)

    analyseur = AnalyseurCorpus()

    arg = sys.argv[1]
    if os.path.isdir(arg):
        analyseur.charger_dossier(arg)
    else:
        # Liste de PDF
        pdfs = [a for a in sys.argv[1:] if a.endswith(".pdf")]
        analyseur.charger_pdfs(pdfs)

    print(analyseur.rapport())

    # Export si demandé
    json_out = [a for a in sys.argv if a.endswith(".json")]
    if json_out:
        analyseur.exporter_json(json_out[0])
