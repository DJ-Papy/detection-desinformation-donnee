"""
MODULE 5 : Analyse de Cadrage Inter-Médias (approche hybride B + A)
====================================================================

Mémoire INSEEC MSc — Data & Marketing Digital — 2025-2026
Problématique : "Dans quelle mesure peut-on détecter de la désinformation
                 médiatique par la donnée ?"

Ce module analyse le RÉGIME 2 (vérifiabilité faible) : les chiffres qui
n'ont pas de référent officiel unique et ne peuvent donc être "fact-checkés".
Ce qui se mesure alors n'est pas la véracité mais le CADRAGE (framing) :
comment différents médias traitent le MÊME événement chiffré.

═══════════════════════════════════════════════════════════════════════
POSITIONNEMENT MÉTHODOLOGIQUE (important pour la soutenance)
═══════════════════════════════════════════════════════════════════════

Approche HYBRIDE, avec une hiérarchie explicite entre les mesures :

  ▸ MESURE PRINCIPALE — B : SÉLECTION DES DONNÉES (inductive, non circulaire)
    Sur l'ensemble des chiffres disponibles pour un événement, quels chiffres
    chaque média choisit de citer ou d'omettre. C'est une mesure OBJECTIVE
    (un chiffre est cité ou non) qui ne présuppose aucun cadre politique.
    → C'est le cœur de l'analyse et la contribution propre du mémoire :
      le cadrage se révèle par la donnée elle-même.

  ▸ MESURE COMPLÉMENTAIRE — A : MARQUEURS DE CADRAGE (déductive, Entman 1993)
    Les 4 fonctions du cadrage (définition du problème, attribution causale,
    jugement moral, remède) repérées par marqueurs lexicaux.
    ⚠️ ASSUMÉ COMME INTERPRÉTATIF : le choix des marqueurs relève du codage
       de l'auteur. Ne sert que d'ÉCLAIRAGE, jamais de preuve isolée.
       (À valider ultérieurement par double-codage humain — non implémenté ici.)

  ▸ MESURE CONTEXTUELLE — acteurs cités (neutre)
    Qui prend la parole dans l'article (gouvernement, opposition, experts...).

ANTI-CIRCULARITÉ
    Contrairement à une approche par "profils éditoriaux pré-calibrés"
    (rejetée : elle construit le résultat qu'elle prétend mesurer), ce module
    ne pose AUCUN profil a priori. Les différences émergent des données.

LIMITES ASSUMÉES
    - Les marqueurs Entman sont aveugles au sens (un même mot peut servir des
      cadrages opposés). D'où leur statut secondaire.
    - La validation par codage humain (kappa de Cohen) reste à faire : le
      module produit une sortie annotable à cette fin (cf. exporter_pour_codage).

Entrée  : groupe d'articles (même événement) + leurs claims (Module 1)
Sortie  : AnalyseCadrage (sélection comparée, signatures Entman, acteurs)

Auteur : Florian, mai 2026.
"""

from __future__ import annotations
import re
import json
import logging
from dataclasses import dataclass, field, asdict
from collections import Counter, defaultdict
from typing import List, Dict, Optional, Tuple, Set

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s")
logger = logging.getLogger("Module5")


# ============================================================================
# STRUCTURES
# ============================================================================

@dataclass
class ArticleCadrage:
    """Un article à analyser pour le cadrage."""
    article_id: str
    media: str
    titre: str
    texte: str
    date: str
    chiffres: List[str] = field(default_factory=list)  # valeurs brutes citées


@dataclass
class SignatureMedia:
    """Signature de cadrage d'un média sur un événement."""
    media: str
    article_id: str
    # Mesure B : sélection des chiffres
    chiffres_cites: List[str] = field(default_factory=list)
    chiffres_exclusifs: List[str] = field(default_factory=list)  # cités par lui seul
    taux_couverture: float = 0.0   # part des chiffres de l'événement qu'il cite
    # Mesure A : signatures Entman (interprétatif)
    entman: Dict[str, int] = field(default_factory=dict)
    fonction_dominante: str = ""
    # Contexte : acteurs cités
    acteurs: Dict[str, int] = field(default_factory=dict)
    pertinent: bool = True
    note: str = ""


@dataclass
class AnalyseCadrage:
    """Résultat de l'analyse de cadrage sur un événement."""
    evenement: str
    n_articles: int
    n_pertinents: int
    chiffres_consensuels: List[str] = field(default_factory=list)  # cités par tous
    chiffres_clivants: Dict[str, List[str]] = field(default_factory=dict)  # chiffre→médias
    signatures: List[SignatureMedia] = field(default_factory=list)
    indice_divergence: float = 0.0  # 0=tous citent pareil, 1=sélections disjointes


# ============================================================================
# MARQUEURS ENTMAN (mesure A — DOCUMENTÉS et ASSUMÉS interprétatifs)
# ============================================================================
# ⚠️ Ces listes constituent le CODEBOOK du mémoire. Chaque marqueur doit
# pouvoir être justifié. Volontairement, on évite les termes politiquement
# orientés (ex : on ne met PAS "précarité" d'un côté et "compétitivité" de
# l'autre, ce qui capterait mécaniquement le clivage gauche/droite).
# Le codebook doit figurer en annexe du mémoire.

CODEBOOK_ENTMAN = {
    "definition_probleme": {
        "description": "Manière de nommer/qualifier la situation",
        "marqueurs": ["crise", "dérapage", "envolée", "alerte", "alarmant",
                      "record", "historique", "inédit", "préoccupant",
                      "explosion", "flambée", "spirale"],
    },
    "attribution_causale": {
        "description": "Désignation des causes/responsables",
        "marqueurs": ["à cause de", "en raison de", "responsable", "faute de",
                      "dû à", "résulte de", "provoqué par", "imputable",
                      "conséquence de", "s'explique par"],
    },
    "jugement_moral": {
        "description": "Évaluation morale explicite",
        "marqueurs": ["scandale", "injuste", "irresponsable", "courage",
                      "rigueur", "laxisme", "gaspillage", "sacrifice",
                      "vertueux", "dérive", "abus"],
    },
    "remede": {
        "description": "Solutions préconisées ou évoquées",
        "marqueurs": ["réforme", "économies", "réduire", "augmenter", "taxer",
                      "supprimer", "investir", "relancer", "coupe", "rabot",
                      "effort budgétaire", "redressement"],
    },
}

# Acteurs (mesure contextuelle neutre)
CODEBOOK_ACTEURS = {
    "gouvernement": ["gouvernement", "ministre", "exécutif", "matignon",
                     "bercy", "élysée", "premier ministre"],
    "opposition": ["opposition", "rassemblement national", "la france insoumise",
                   "les républicains", "parti socialiste", "écologistes"],
    "experts": ["économiste", "cour des comptes", "ofce", "institut",
                "chercheur", "analyste"],
    "corps_sociaux": ["syndicat", "patronat", "medef", "cgt", "fédération",
                      "association"],
    "institutions_eu": ["commission européenne", "bruxelles", "bce",
                         "agences de notation"],
}


# ============================================================================
# MODULE 5
# ============================================================================

class Module5Cadrage:
    """Analyse le cadrage différentiel d'un événement entre médias."""

    def __init__(self, seuil_pertinence: int = 2):
        """
        Args:
            seuil_pertinence: nb min de chiffres OU de mots-clés événement
                              pour considérer un article comme pertinent.
        """
        self.seuil_pertinence = seuil_pertinence

    def analyser_evenement(
        self, evenement: str, articles: List[ArticleCadrage],
        mots_cles_evenement: Optional[List[str]] = None
    ) -> AnalyseCadrage:
        """
        Analyse le cadrage d'un événement couvert par plusieurs médias.

        Args:
            evenement: libellé de l'événement (ex: "déficit 2023")
            articles: liste des articles candidats
            mots_cles_evenement: mots qui doivent apparaître pour qu'un article
                                 soit jugé pertinent (filtre anti-faux-positifs)
        """
        # 1. Filtrer les articles réellement pertinents
        pertinents = []
        for art in articles:
            est_pertinent, note = self._est_pertinent(art, mots_cles_evenement)
            if est_pertinent:
                pertinents.append(art)
            else:
                logger.info(f"Article écarté (non pertinent) : "
                            f"[{art.media}] {art.titre[:40]} — {note}")

        if not pertinents:
            return AnalyseCadrage(evenement, len(articles), 0)

        # 2. Mesure B : univers des chiffres de l'événement
        tous_chiffres = self._normaliser_chiffres(pertinents)
        univers = set()
        for art in pertinents:
            univers |= set(tous_chiffres[art.article_id])

        # 3. Construire les signatures par média
        signatures = []
        for art in pertinents:
            sig = self._signature(art, tous_chiffres[art.article_id],
                                  univers, pertinents, tous_chiffres)
            signatures.append(sig)

        # 4. Chiffres consensuels (cités par tous) vs clivants
        consensuels, clivants = self._consensus_clivage(pertinents, tous_chiffres)

        # 5. Indice de divergence des sélections
        idiv = self._indice_divergence(signatures, univers)

        return AnalyseCadrage(
            evenement=evenement,
            n_articles=len(articles),
            n_pertinents=len(pertinents),
            chiffres_consensuels=sorted(consensuels),
            chiffres_clivants=clivants,
            signatures=signatures,
            indice_divergence=idiv,
        )

    # ---- Pertinence (filtre anti-faux-positifs) ----

    def _est_pertinent(self, art: ArticleCadrage,
                       mots_cles: Optional[List[str]]) -> Tuple[bool, str]:
        """Un article est pertinent s'il contient les mots-clés de l'événement."""
        if not mots_cles:
            # Sans mots-clés fournis : pertinent s'il a assez de chiffres
            return (len(art.chiffres) >= self.seuil_pertinence,
                    f"{len(art.chiffres)} chiffres")
        txt = (art.titre + " " + art.texte).lower()
        hits = sum(1 for mc in mots_cles if mc.lower() in txt)
        if hits >= 1:
            return True, f"{hits} mot(s)-clé(s)"
        return False, "aucun mot-clé de l'événement"

    # ---- Mesure B : sélection des chiffres ----

    def _normaliser_chiffres(self, articles: List[ArticleCadrage]
                            ) -> Dict[str, List[str]]:
        """
        Normalise les chiffres pour pouvoir les comparer entre articles.
        Ex : "5,5 %", "5,5%", "5,5 pour cent" → "5.5%"
        """
        result = {}
        for art in articles:
            normalises = []
            for c in art.chiffres:
                n = self._normaliser_un_chiffre(c)
                if n:
                    normalises.append(n)
            result[art.article_id] = normalises
        return result

    def _normaliser_un_chiffre(self, brut: str) -> str:
        """Normalise un chiffre individuel en clé comparable."""
        b = brut.lower().strip()
        # Extraire le nombre
        m = re.search(r'(\d+(?:[.,]\d+)?)', b)
        if not m:
            return ""
        nombre = m.group(1).replace(',', '.')
        # Détecter l'unité
        if '%' in b or 'pour cent' in b or 'point' in b:
            unite = '%'
        elif 'milliard' in b:
            unite = 'Md'
        elif 'million' in b:
            unite = 'M'
        else:
            unite = ''
        return f"{nombre}{unite}"

    def _signature(self, art: ArticleCadrage, chiffres_art: List[str],
                   univers: Set[str], tous_arts: List[ArticleCadrage],
                   tous_chiffres: Dict[str, List[str]]) -> SignatureMedia:
        """Construit la signature de cadrage d'un média."""
        chiffres_set = set(chiffres_art)

        # Chiffres exclusifs : cités par lui et personne d'autre
        autres_chiffres = set()
        for other in tous_arts:
            if other.article_id != art.article_id:
                autres_chiffres |= set(tous_chiffres[other.article_id])
        exclusifs = chiffres_set - autres_chiffres

        taux = len(chiffres_set) / len(univers) if univers else 0.0

        # Mesure A : Entman
        entman = self._scorer_entman(art.texte)
        dominante = max(entman, key=entman.get) if any(entman.values()) else ""

        # Acteurs
        acteurs = self._scorer_acteurs(art.texte)

        return SignatureMedia(
            media=art.media,
            article_id=art.article_id,
            chiffres_cites=sorted(chiffres_set),
            chiffres_exclusifs=sorted(exclusifs),
            taux_couverture=round(taux, 2),
            entman=entman,
            fonction_dominante=dominante,
            acteurs=acteurs,
        )

    # ---- Mesure A : Entman (interprétatif) ----

    def _scorer_entman(self, texte: str) -> Dict[str, int]:
        """Compte les marqueurs de chaque fonction de cadrage."""
        t = texte.lower()
        scores = {}
        for fonction, fiche in CODEBOOK_ENTMAN.items():
            scores[fonction] = sum(1 for m in fiche["marqueurs"] if m in t)
        return scores

    def _scorer_acteurs(self, texte: str) -> Dict[str, int]:
        """Compte les mentions d'acteurs par catégorie."""
        t = texte.lower()
        scores = {}
        for categorie, marqueurs in CODEBOOK_ACTEURS.items():
            n = sum(t.count(m) for m in marqueurs)
            if n > 0:
                scores[categorie] = n
        return scores

    # ---- Consensus / clivage ----

    def _consensus_clivage(self, articles: List[ArticleCadrage],
                           tous_chiffres: Dict[str, List[str]]
                           ) -> Tuple[Set[str], Dict[str, List[str]]]:
        """Identifie les chiffres cités par tous vs par certains seulement."""
        n = len(articles)
        compteur = defaultdict(list)  # chiffre → liste des médias qui le citent
        for art in articles:
            for c in set(tous_chiffres[art.article_id]):
                compteur[c].append(art.media)

        consensuels = {c for c, medias in compteur.items() if len(medias) == n}
        clivants = {c: sorted(set(medias)) for c, medias in compteur.items()
                    if 1 <= len(medias) < n}
        return consensuels, clivants

    def _indice_divergence(self, signatures: List[SignatureMedia],
                           univers: Set[str]) -> float:
        """
        Indice [0,1] : à quel point les médias sélectionnent des chiffres
        différents. 0 = tous citent les mêmes chiffres ; 1 = sélections
        totalement disjointes. Basé sur le ratio chiffres exclusifs / univers.
        """
        if not univers or not signatures:
            return 0.0
        total_exclusifs = sum(len(s.chiffres_exclusifs) for s in signatures)
        return round(total_exclusifs / len(univers), 2)

    # ---- Rapport ----

    def rapport(self, analyse: AnalyseCadrage) -> str:
        """Génère un rapport lisible de l'analyse."""
        L = []
        L.append("=" * 68)
        L.append(f"ANALYSE DE CADRAGE — {analyse.evenement}")
        L.append("=" * 68)
        L.append(f"Articles analysés : {analyse.n_pertinents}/{analyse.n_articles} "
                 f"(après filtre de pertinence)")
        L.append(f"Indice de divergence des sélections : {analyse.indice_divergence} "
                 f"(0=identique, 1=disjoint)")

        L.append(f"\n▸ CHIFFRES CONSENSUELS (cités par tous les médias) :")
        L.append(f"  {', '.join(analyse.chiffres_consensuels) or '(aucun)'}")

        L.append(f"\n▸ CADRAGE PAR MÉDIA (mesure B : sélection des chiffres)")
        for s in analyse.signatures:
            L.append(f"\n  [{s.media}] couverture {s.taux_couverture:.0%} de l'univers chiffré")
            L.append(f"    Chiffres exclusifs (cités par lui seul) : "
                     f"{', '.join(s.chiffres_exclusifs) or '(aucun)'}")
            L.append(f"    Cadrage Entman dominant : {s.fonction_dominante or 'n/a'} "
                     f"{dict(s.entman)}")
            top_acteurs = sorted(s.acteurs.items(), key=lambda x: -x[1])[:3]
            L.append(f"    Acteurs cités : "
                     f"{', '.join(f'{a}({n})' for a,n in top_acteurs) or 'n/a'}")

        L.append(f"\n▸ INTERPRÉTATION")
        L.append(f"  La sélection différenciée des chiffres (indice {analyse.indice_divergence}) "
                 f"révèle des cadrages distincts du même fait, sans recours")
        L.append(f"  à des profils éditoriaux a priori. Les marqueurs Entman")
        L.append(f"  (mesure A) sont fournis à titre d'éclairage complémentaire.")
        return "\n".join(L)

    def exporter_pour_codage(self, analyse: AnalyseCadrage, chemin: str):
        """
        Exporte une grille annotable pour la validation humaine ultérieure
        (double-codage → kappa de Cohen). Non utilisé maintenant mais prêt.
        """
        import csv
        with open(chemin, "w", encoding="utf-8", newline="") as f:
            w = csv.writer(f)
            w.writerow(["article_id", "media", "fonction_entman_auto",
                        "fonction_entman_codeur1", "fonction_entman_codeur2"])
            for s in analyse.signatures:
                w.writerow([s.article_id, s.media, s.fonction_dominante, "", ""])
        logger.info(f"Grille de codage exportée : {chemin}")


# ============================================================================
# TESTS / DÉMO
# ============================================================================

def demo():
    """Démonstration sur des articles fictifs simulant l'événement déficit."""
    print("\n" + "=" * 68)
    print("DÉMO — MODULE 5 sur un événement simulé")
    print("=" * 68)

    articles = [
        ArticleCadrage(
            "art_figaro", "Le Figaro", "L'envolée du déficit à 5,5%",
            "Le déficit atteint 5,5% du PIB, un dérapage grave. La dette grimpe "
            "à 110,6%. Le gouvernement doit faire des économies : 10 milliards, "
            "voire 50 milliards. La rigueur budgétaire s'impose, un effort de "
            "réforme est nécessaire pour réduire la dépense.",
            "2024-03-27",
            ["5,5 %", "110,6 %", "10 milliards", "50 milliards"]),
        ArticleCadrage(
            "art_libe", "Libération", "Taxation des plus riches",
            "Face au déficit de 5,5%, une autre voie : taxer les plus riches "
            "pourrait rapporter 42 milliards. Les recettes fiscales pourraient "
            "augmenter de 20 milliards. Plutôt que des économies sur les services "
            "publics, un effort de justice fiscale.",
            "2024-03-27",
            ["5,5 %", "42 milliards", "20 milliards"]),
        ArticleCadrage(
            "art_monde", "Le Monde", "Le dérapage du déficit embarrasse le gouvernement",
            "Le déficit s'établit à 5,5%, en raison d'un ralentissement. La dette "
            "atteint 110,6%. Le gouvernement, responsable de la trajectoire, doit "
            "trouver 21 milliards. Une réforme et des économies sont à l'étude.",
            "2024-03-27",
            ["5,5 %", "110,6 %", "21 milliards"]),
        # Faux positif : article dans la fenêtre mais hors sujet
        ArticleCadrage(
            "art_hs", "Le Point", "Des leçons de vie face à la mort",
            "Un témoignage bouleversant sur la fin de vie et le deuil.",
            "2024-03-27", ["85 %"]),
    ]

    m5 = Module5Cadrage()
    analyse = m5.analyser_evenement(
        "déficit public 2023",
        articles,
        mots_cles_evenement=["déficit", "dette", "pib", "budgétaire"]
    )
    print(m5.rapport(analyse))


if __name__ == "__main__":
    demo()
