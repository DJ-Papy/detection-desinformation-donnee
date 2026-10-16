"""
MODULE 1.5 : Classifieur de Régime de Vérifiabilité
====================================================

Mémoire INSEEC MSc — Data & Marketing Digital — 2025-2026
Problématique : "Dans quelle mesure peut-on détecter de la désinformation
                 médiatique par la donnée ?"

Ce module classe chaque claim chiffré extrait (Module 1) dans l'un des deux
RÉGIMES DE VÉRIFIABILITÉ qui structurent l'analyse du mémoire :

  RÉGIME 1 — VÉRIFIABILITÉ FORTE
    Le chiffre renvoie à une série statistique officielle unique et
    identifiable (INSEE, Eurostat). Un verdict de véracité est possible.
    → aiguillé vers M2 → M3 → M4 (fact-checking numérique)
    Exemples : "l'inflation s'établit à 4,3% selon l'Insee"
               "le taux de chômage atteint 7,5% au T4"

  RÉGIME 2 — VÉRIFIABILITÉ FAIBLE
    Le chiffre n'a pas de référent officiel unique : objectif politique,
    prévision, estimation sectorielle, donnée disputée. La question
    "est-ce vrai ?" est mal posée. Seul le CADRAGE est analysable.
    → aiguillé vers M5 (analyse de framing)
    Exemples : "objectif de 20 milliards d'économies"
               "le déficit hospitalier s'élève à 1,7 milliard"
               "120 signatures de députés"

POSITIONNEMENT THÉORIQUE
    Cette distinction opérationnalise la thèse centrale du mémoire :
    la détectabilité de la désinformation par la donnée n'est PAS uniforme.
    Elle est élevée en régime 1, quasi nulle en régime 2 — où la donnée
    chiffrée produit une "illusion d'objectivité" (cf. limites du fact-
    checking automatique, Graves 2018 ; Nyhan & Reifler 2010).

MÉTHODE
    Classification par règles interprétables (marqueurs linguistiques +
    appariement à la grille des indicateurs officiels). Choix de
    l'interprétabilité plutôt que d'un classifieur ML opaque : chaque
    décision de régime doit pouvoir être justifiée au lecteur/jury.

Entrée  : ClaimStructure (Module 2) OU ClaimCandidat (Module 1) + phrase
Sortie  : RegimeVerifiabilite (régime, score, justification, marqueurs)

Auteur : Florian, mai 2026.
"""

from __future__ import annotations
import re
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional, Dict, Tuple

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
logger = logging.getLogger("Module1.5")


# ============================================================================
# STRUCTURES
# ============================================================================

class Regime(Enum):
    """Les deux régimes de vérifiabilité + un cas indéterminé."""
    FORTE = "regime_1_verifiabilite_forte"
    FAIBLE = "regime_2_verifiabilite_faible"
    INDETERMINE = "indetermine"


@dataclass
class RegimeVerifiabilite:
    """Résultat de la classification d'un claim."""
    claim_id: str
    regime: Regime
    score_confiance: float          # 0..1 : fiabilité de la classification
    indicateur_officiel: str        # nom de l'indicateur si régime 1, sinon ""
    marqueurs_detectes: Dict[str, List[str]] = field(default_factory=dict)
    justification: str = ""

    @property
    def aiguillage(self) -> str:
        """Vers quelle suite du pipeline ce claim doit être routé."""
        if self.regime == Regime.FORTE:
            return "M2→M3→M4 (fact-checking numérique)"
        elif self.regime == Regime.FAIBLE:
            return "M5 (analyse de framing)"
        return "revue manuelle"


# ============================================================================
# CLASSIFIEUR
# ============================================================================

class ClassifieurRegime:
    """
    Classe un claim dans son régime de vérifiabilité par un faisceau
    d'indices linguistiques et sémantiques.

    Logique de décision (par accumulation de preuves) :
      + Indices RÉGIME 1 : indicateur macro standard + attribution à une
        source officielle + verbe d'état (constat) + unité % cohérente
      + Indices RÉGIME 2 : verbe de prévision/intention + attribution à un
        acteur politique + grandeur budgétaire (milliards/millions €) +
        marqueurs de projection temporelle future
    """

    # --- Indicateurs à référent officiel unique (régime 1) ---
    # Reliés à la grille des événements INSEE
    INDICATEURS_OFFICIELS = {
        "inflation": ["inflation", "indice des prix", "prix à la consommation",
                      "ipc", "ipch", "hausse des prix"],
        "chômage": ["taux de chômage", "chômage au sens du bit", "chômeurs au sens"],
        "PIB": ["produit intérieur brut", "pib", "croissance du pib",
                "croissance économique"],
        "dette": ["dette publique", "dette au sens de maastricht",
                  "dette de la france"],
        "déficit": ["déficit public", "déficit budgétaire"],  # frontière régime 1/2
    }

    # --- Sources officielles (renforce régime 1) ---
    SOURCES_OFFICIELLES = [
        "insee", "institut national de la statistique", "eurostat",
        "comptes nationaux", "banque de france",
    ]

    # --- Verbes d'état / constat (régime 1) ---
    VERBES_CONSTAT = [
        "s'établit", "s'établissant", "atteint", "a atteint", "ressort à",
        "se situe", "s'affiche", "s'élève à", "est de", "était de",
        "a progressé de", "a augmenté de", "a reculé de", "a diminué de",
        "a ralenti", "a rebondi", "s'est établi",
    ]

    # --- Verbes / marqueurs de prévision et intention (régime 2) ---
    MARQUEURS_PREVISION = [
        "objectif", "vise", "viserait", "devront", "devrait", "pourrait",
        "prévoit", "prévu", "prévision", "attendu", "espère", "anticipe", "projette",
        "à hauteur de", "estimé à", "estimée à", "évalué à", "évaluée à",
        "selon nos estimations", "calculent", "plaide pour", "réclame",
        "demande", "promet", "annonce un", "ambition",
        # Projections temporelles futures (objectifs datés) → régime 2
        "d'ici", "d'ici à", "à l'horizon", "fin du quinquennat", "à terme",
        "en 2025", "en 2026", "en 2027", "il faudrait", "permettrait",
        "atteindre", "ramener à", "tomber à", "se rapprocher de",
    ]

    # --- Marqueurs politiques / d'acteur (régime 2) ---
    MARQUEURS_ACTEUR_POLITIQUE = [
        "ministre", "gouvernement", "député", "sénateur", "président",
        "exécutif", "matignon", "bercy", "élysée", "fédération",
        "syndicat", "patron de", "économiste", "selon le", "selon la",
        "a annoncé", "a déclaré", "a affirmé", "plaide", "rapport",
    ]

    # --- Grandeurs typiquement budgétaires / politiques (régime 2) ---
    # Les "milliards d'euros" sont rarement des séries INSEE directes
    # (sauf dette/PIB en niveau), plus souvent des budgets/dépenses/objectifs
    UNITES_BUDGETAIRES = ["milliard", "milliards", "million", "millions"]

    def classer(
        self,
        claim_id: str,
        phrase: str,
        indicateur_m2: str = "",
        unite_m2: str = "",
        est_variation: bool = False,
        modificateur: str = "",
    ) -> RegimeVerifiabilite:
        """
        Classe un claim.

        Args:
            claim_id: identifiant du claim
            phrase: phrase source contenant le claim
            indicateur_m2: indicateur détecté par le Module 2 (optionnel)
            unite_m2: unité détectée par le Module 2 (optionnel)
            est_variation: le claim porte-t-il sur une variation
            modificateur: modificateur détecté ("environ", "près de"...)

        Returns:
            RegimeVerifiabilite
        """
        p = phrase.lower()
        marqueurs = {
            "indicateur_officiel": [],
            "source_officielle": [],
            "verbe_constat": [],
            "prevision": [],
            "acteur_politique": [],
            "unite_budgetaire": [],
        }

        # --- Détection indices RÉGIME 1 ---
        indicateur_trouve = ""
        for indic, kws in self.INDICATEURS_OFFICIELS.items():
            for kw in kws:
                if kw in p:
                    marqueurs["indicateur_officiel"].append(kw)
                    if not indicateur_trouve:
                        indicateur_trouve = indic
        # Renfort via l'indicateur du Module 2
        if indicateur_m2 and indicateur_m2 in self.INDICATEURS_OFFICIELS:
            if not indicateur_trouve:
                indicateur_trouve = indicateur_m2

        for src in self.SOURCES_OFFICIELLES:
            if src in p:
                marqueurs["source_officielle"].append(src)

        for v in self.VERBES_CONSTAT:
            if v in p:
                marqueurs["verbe_constat"].append(v)

        # --- Détection indices RÉGIME 2 ---
        for m in self.MARQUEURS_PREVISION:
            if m in p:
                marqueurs["prevision"].append(m)

        for m in self.MARQUEURS_ACTEUR_POLITIQUE:
            if m in p:
                marqueurs["acteur_politique"].append(m)

        for u in self.UNITES_BUDGETAIRES:
            if u in p:
                marqueurs["unite_budgetaire"].append(u)
                break

        # --- Calcul des scores ---
        score_r1 = (
            2.0 * bool(marqueurs["indicateur_officiel"])
            + 2.0 * bool(marqueurs["source_officielle"])
            + 1.0 * bool(marqueurs["verbe_constat"])
            + 0.5 * (unite_m2 == "%")
        )
        score_r2 = (
            2.0 * bool(marqueurs["prevision"])
            + 1.0 * bool(marqueurs["acteur_politique"])
            + 1.0 * bool(marqueurs["unite_budgetaire"])
        )

        # --- Règles de décision ---
        # Cas fort régime 1 : indicateur officiel + (source OU verbe constat),
        # sans signal de prévision dominant
        regime, justification = self._decider(
            score_r1, score_r2, marqueurs, indicateur_trouve
        )

        # Score de confiance : écart normalisé entre les deux scores
        total = score_r1 + score_r2
        if total == 0:
            confiance = 0.3  # aucun marqueur : faible confiance
        else:
            confiance = abs(score_r1 - score_r2) / total
            confiance = round(min(0.95, 0.4 + 0.55 * confiance), 2)

        return RegimeVerifiabilite(
            claim_id=claim_id,
            regime=regime,
            score_confiance=confiance,
            indicateur_officiel=indicateur_trouve if regime == Regime.FORTE else "",
            marqueurs_detectes={k: v for k, v in marqueurs.items() if v},
            justification=justification,
        )

    def _decider(
        self, score_r1: float, score_r2: float,
        marqueurs: Dict, indicateur: str
    ) -> Tuple[Regime, str]:
        """Applique les règles de décision et retourne (régime, justification)."""

        a_indic = bool(marqueurs["indicateur_officiel"])
        a_source = bool(marqueurs["source_officielle"])
        a_prevision = bool(marqueurs["prevision"])
        a_budget = bool(marqueurs["unite_budgetaire"])
        a_constat = bool(marqueurs["verbe_constat"])

        # Règle 0 (PRIORITAIRE) : une prévision/objectif sur un indicateur, sans
        # attribution à une source officielle qui CONSTATE, reste du régime 2.
        # Ex : "le chômage pourrait tomber à 5% d'ici 2027" → objectif, pas constat.
        # Ex : "la Banque de France prévoit un chômage de 7,2%" → prévision.
        # Distinction clé : un constat INSEE ("l'Insee indique 7,4%") n'est PAS
        # une prévision même si le mot "prévision" apparaît dans le contexte large.
        if a_prevision and not (a_source and a_constat):
            return Regime.FAIBLE, (
                "Marqueur de prévision/objectif présent sans constat attribué à "
                "une source officielle : chiffre prospectif → régime 2 (cadrage). "
                "La valeur n'est pas un fait mesuré mais une projection."
            )

        # Règle 1 : indicateur officiel + source officielle = régime 1 quasi certain
        if a_indic and a_source and not a_prevision:
            return Regime.FORTE, (
                f"Indicateur officiel ({indicateur}) attribué à une source "
                f"officielle, sans marqueur de prévision."
            )

        # Règle 2 : prévision + grandeur budgétaire = régime 2 net
        if a_prevision and a_budget:
            return Regime.FAIBLE, (
                "Grandeur budgétaire associée à un marqueur de prévision/"
                "objectif : chiffre prospectif sans référent officiel unique."
            )

        # Règle 3 : indicateur officiel + verbe de constat, pas de prévision
        if a_indic and score_r1 > score_r2:
            return Regime.FORTE, (
                f"Indicateur officiel ({indicateur}) avec verbe de constat ; "
                f"score régime 1 ({score_r1}) > régime 2 ({score_r2})."
            )

        # Règle 4 : grandeur budgétaire + acteur politique, pas d'indicateur officiel
        if a_budget and not a_indic:
            return Regime.FAIBLE, (
                "Grandeur budgétaire sans indicateur statistique officiel : "
                "dépense/objectif/estimation relevant du cadrage."
            )

        # Règle 5 : décision par score
        if score_r1 > score_r2:
            return Regime.FORTE, f"Score régime 1 ({score_r1}) > régime 2 ({score_r2})."
        elif score_r2 > score_r1:
            return Regime.FAIBLE, f"Score régime 2 ({score_r2}) > régime 1 ({score_r1})."

        return Regime.INDETERMINE, (
            "Aucun faisceau d'indices dominant : nécessite une revue manuelle."
        )


# ============================================================================
# TESTS UNITAIRES
# ============================================================================

def tests_unitaires():
    print("\n" + "=" * 64)
    print("TESTS UNITAIRES — MODULE 1.5 : CLASSIFIEUR DE RÉGIME")
    print("=" * 64)

    clf = ClassifieurRegime()
    erreurs, total = 0, 0

    cas = [
        # (phrase, indicateur_m2, unite_m2, régime attendu, libellé)
        ("L'inflation s'établit à 4,3% sur un an en juillet, selon l'Insee.",
         "inflation", "%", Regime.FORTE, "Inflation + Insee"),
        ("Le taux de chômage atteint 7,5% au quatrième trimestre, indique l'Insee.",
         "chômage", "%", Regime.FORTE, "Chômage + Insee"),
        ("L'objectif est de 20 milliards d'euros d'économies pour 2025.",
         "", "milliards €", Regime.FAIBLE, "Objectif budgétaire"),
        ("Le déficit des hôpitaux s'élève à 1,7 milliard d'euros pour 2023.",
         "", "milliards €", Regime.FAIBLE, "Estimation sectorielle"),
        ("Le PIB a progressé de 0,2% au deuxième trimestre, selon l'Insee.",
         "PIB", "%", Regime.FORTE, "PIB + Insee"),
        ("Le gouvernement prévoit une croissance de 1,4% en 2024.",
         "PIB", "%", Regime.FAIBLE, "Prévision politique"),
        ("Ces dernières devront s'élever à 20 milliards d'euros.",
         "", "milliards €", Regime.FAIBLE, "Intention budgétaire"),
        ("La dette publique a reculé à 111,8% du PIB, selon l'Insee.",
         "dette", "%", Regime.FORTE, "Dette + Insee"),
    ]

    for phrase, ind, unite, attendu, libelle in cas:
        total += 1
        res = clf.classer("TEST", phrase, indicateur_m2=ind, unite_m2=unite)
        ok = res.regime == attendu
        symbole = "✅" if ok else "❌"
        if not ok:
            erreurs += 1
        print(f"{symbole} {libelle:30s} → {res.regime.value:35s} (conf={res.score_confiance})")
        if not ok:
            print(f"     Attendu : {attendu.value}")
            print(f"     Justif  : {res.justification}")

    print(f"\nRésultat : {total - erreurs}/{total} tests passés.")
    return erreurs == 0


if __name__ == "__main__":
    tests_unitaires()
