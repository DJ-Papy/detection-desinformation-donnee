"""
MODULE 4 : Validation Numérique — VERSION RÉVISÉE
==================================================

Mémoire INSEEC MSc — Data & Marketing Digital — 2025-2026
Problématique : "Dans quelle mesure peut-on détecter de la désinformation
                 médiatique par la donnée ?"

Ce module confronte un claim chiffré (régime 1) à la valeur officielle INSEE
(récupérée par M3) et produit un VERDICT de vérification.

═══════════════════════════════════════════════════════════════════════
CE QUI CHANGE PAR RAPPORT À LA VERSION ORIGINALE (réponse à l'audit)
═══════════════════════════════════════════════════════════════════════

L'audit jugeait M4 "solide" mais pointait un défaut : les seuils de tolérance
(2%, 8%, 20% d'écart relatif) étaient ARBITRAIRES. Un jury demanderait
légitimement "pourquoi 2% et pas 1% ?".

CETTE VERSION ANCRE LES SEUILS DANS DEUX PRINCIPES MESURABLES :

  1. L'ARRONDI JOURNALISTIQUE LÉGITIME
     Un journaliste qui écrit "4,3%" pour une valeur INSEE de 4,28% n'a pas
     désinformé : il a arrondi à la précision d'usage (1 décimale). Le seuil
     "confirmé" correspond donc à la demi-unité du dernier chiffre significatif
     publié par le média (ex : "4,3%" → tolérance ±0,05 point).

  2. L'INTERVALLE DE CONFIANCE DE LA STATISTIQUE INSEE
     Le taux de chômage BIT est publié AVEC une marge d'incertitude (≈±0,3
     point, source INSEE). Un écart inférieur à l'incertitude de la mesure
     elle-même ne peut PAS être qualifié d'erreur factuelle.
     ⚠️ Ces marges sont à confirmer dans les notes méthodologiques INSEE
        de chaque indicateur (intervention manuelle requise — cf. notes).

  → Le seuil "confirmé" = max(arrondi journalistique, IC INSEE).
     C'est défendable : on ne sanctionne un écart que s'il dépasse à la fois
     la précision d'écriture du journaliste ET l'incertitude de la source.

VERDICTS (inchangés, clarifiés)
  CONFIRME      : écart compatible avec arrondi + IC → le chiffre est fidèle
  APPROXIMATIF  : écart modéré, explicable (arrondi large, valeur provisoire)
  IMPRECIS      : écart notable, à investiguer (signal faible de distorsion)
  INCORRECT     : écart majeur incompatible avec une erreur d'arrondi
  INDETERMINE   : impossible de trancher (donnée manquante, période ambiguë)

LIMITES ASSUMÉES
  - Un verdict "INCORRECT" ne prouve PAS une intention de désinformer
    (cf. distinction mis/disinformation, Wardle 2017). Il signale un écart
    factuel, dont l'interprétation reste qualitative.
  - Les marges d'IC INSEE doivent être renseignées indicateur par indicateur.

Entrée  : claim structuré (M2) + DonneeOfficielle (M3)
Sortie  : ResultatValidation (verdict + écart + justification traçable)

Auteur : Florian, mai 2026.
"""

from __future__ import annotations
import re
import math
import logging
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Optional, Dict, Any, Tuple

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s")
logger = logging.getLogger("Module4")


# ============================================================================
# VERDICTS & TYPES
# ============================================================================

class Verdict(Enum):
    CONFIRME = "confirmé"
    APPROXIMATIF = "approximatif"
    IMPRECIS = "imprécis"
    INCORRECT = "incorrect"
    INDETERMINE = "indéterminé"


class CategorieIndicateur(Enum):
    TAUX = "taux"                 # % (chômage, inflation)
    INDICE = "indice"             # indices de prix
    VOLUME_MILLIARDS = "volume"   # PIB, dette, déficit en Md€ ou % PIB
    POPULATION = "population"     # démographie
    VARIATION = "variation"       # variations en points


# ============================================================================
# MARGES D'INCERTITUDE INSEE (à confirmer — intervention manuelle)
# ============================================================================
# ⚠️ Ces marges (demi-IC à 95%, en valeur absolue de l'unité) doivent être
# confirmées dans les notes méthodologiques INSEE de chaque indicateur.
# Valeurs de départ raisonnables, sourcées approximativement :
#   - chômage BIT : l'INSEE publie un IC d'environ ±0,3 point (enquête Emploi)
#   - inflation IPC : quasi-exhaustif, incertitude faible (~0,1 point)
#   - PIB : révisions plus importantes que l'IC ; on retient ~0,2 point
# Ces valeurs servent de PLANCHER au seuil "confirmé".

IC_INSEE = {
    "chômage": 0.3,      # ±0,3 point (à confirmer note Enquête Emploi)
    "inflation": 0.1,    # ±0,1 point
    "PIB": 0.2,          # ±0,2 point (révisions)
    "dette": 0.1,        # % PIB
    "déficit": 0.1,      # % PIB
}


# ============================================================================
# STRUCTURES
# ============================================================================

@dataclass
class ClaimAValider:
    claim_id: str
    valeur_claim: float
    valeur_brute: str            # texte original "4,3 %"
    indicateur: str
    unite: str
    phrase_originale: str = ""
    est_variation: bool = False
    est_prevision: bool = False
    modificateur: str = ""       # "environ", "près de"...


@dataclass
class DonneeOfficielle:
    indicateur: str
    valeur_officielle: Optional[float]
    periode: str
    unite: str
    source: str = "INSEE"
    libelle: str = ""
    trouve: bool = True


@dataclass
class ResultatValidation:
    claim_id: str
    verdict: Verdict
    valeur_claim: float
    valeur_officielle: Optional[float]
    ecart_absolu: Optional[float] = None
    ecart_relatif: Optional[float] = None
    seuil_confirme_applique: Optional[float] = None
    score_confiance: float = 0.0
    justification: str = ""
    composantes_seuil: Dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["verdict"] = self.verdict.value
        return d


# ============================================================================
# ANALYSEUR DE CONTEXTE (conservé de l'original, allégé)
# ============================================================================

class AnalyseurContexte:
    """Détecte les modificateurs qui ajustent la tolérance."""

    MODIFICATEURS_APPROXIMATION = {
        "environ": 0.05, "près de": 0.05, "autour de": 0.05,
        "approximativement": 0.05, "presque": 0.05, "quasiment": 0.05,
        "plus de": 0.08, "moins de": 0.08, "près des": 0.05,
    }

    MARQUEURS_PROVISOIRE = [
        "estimation flash", "chiffres provisoires", "première estimation",
        "données préliminaires", "estimé à", "selon une première",
    ]

    def analyser(self, claim: ClaimAValider) -> Dict[str, Any]:
        texte = claim.phrase_originale.lower()
        resultat = {
            "modificateur": "", "tolerance_modificateur": None,
            "est_provisoire": False,
        }
        for mod, seuil in self.MODIFICATEURS_APPROXIMATION.items():
            if mod in texte:
                resultat["modificateur"] = mod
                resultat["tolerance_modificateur"] = seuil
                break
        for m in self.MARQUEURS_PROVISOIRE:
            if m in texte:
                resultat["est_provisoire"] = True
                break
        return resultat


# ============================================================================
# CALCUL DES SEUILS JUSTIFIÉS (cœur de la révision)
# ============================================================================

class SeuilsJustifies:
    """
    Calcule les seuils de verdict à partir de principes mesurables plutôt
    que de valeurs arbitraires.
    """

    @staticmethod
    def precision_arrondi(valeur_brute: str) -> float:
        """
        Déduit la tolérance d'arrondi journalistique à partir du nombre de
        décimales écrites par le média.

        "4,3%"  → 1 décimale → demi-unité = 0,05  (le journaliste a arrondi
                  à 0,1 près, donc la vraie valeur est dans [4,25 ; 4,35[)
        "4,28%" → 2 décimales → 0,005
        "5%"    → 0 décimale → 0,5
        "110,6%"→ 1 décimale → 0,05

        Returns:
            demi-unité du dernier chiffre significatif (en valeur absolue)
        """
        m = re.search(r'\d+(?:[.,](\d+))?', valeur_brute.replace(' ', ''))
        if not m:
            return 0.5
        decimales = m.group(1)
        n_dec = len(decimales) if decimales else 0
        # demi-unité du dernier chiffre = 0.5 * 10^(-n_dec)
        return 0.5 * (10 ** (-n_dec))

    @staticmethod
    def seuil_confirme(claim: ClaimAValider, ic_insee: float) -> Tuple[float, Dict]:
        """
        Seuil "confirmé" = max(arrondi journalistique, IC INSEE).

        On ne qualifie un écart de suspect que s'il dépasse À LA FOIS :
          - la précision d'écriture du journaliste (arrondi légitime)
          - l'incertitude statistique de la mesure INSEE
        """
        arrondi = SeuilsJustifies.precision_arrondi(claim.valeur_brute)
        seuil = max(arrondi, ic_insee)
        composantes = {
            "arrondi_journalistique": round(arrondi, 4),
            "ic_insee": round(ic_insee, 4),
            "seuil_retenu": round(seuil, 4),
        }
        return seuil, composantes


# ============================================================================
# VALIDATEUR
# ============================================================================

class Module4Validation:
    """Produit un verdict de vérification pour un claim régime 1."""

    def __init__(self):
        self.contexte = AnalyseurContexte()
        self.seuils = SeuilsJustifies()

    def valider(self, claim: ClaimAValider,
                donnee: DonneeOfficielle) -> ResultatValidation:
        """Valide un claim contre la donnée officielle."""

        # 1. Données manquantes → indéterminé
        if not donnee.trouve or donnee.valeur_officielle is None:
            return ResultatValidation(
                claim.claim_id, Verdict.INDETERMINE,
                claim.valeur_claim, None,
                justification="Donnée officielle indisponible : "
                              "impossible de trancher.")

        # 2. Analyse du contexte
        ctx = self.contexte.analyser(claim)

        # 3. Écarts
        ecart_absolu = abs(claim.valeur_claim - donnee.valeur_officielle)
        if donnee.valeur_officielle != 0:
            ecart_relatif = ecart_absolu / abs(donnee.valeur_officielle)
        else:
            ecart_relatif = float('inf') if ecart_absolu > 0 else 0.0

        # 4. Seuil "confirmé" justifié
        ic = IC_INSEE.get(claim.indicateur, 0.1)
        seuil_conf, composantes = self.seuils.seuil_confirme(claim, ic)

        # Si modificateur d'approximation ("environ"), élargir le seuil confirmé
        if ctx["tolerance_modificateur"] is not None:
            # le modificateur autorise un écart relatif → convertir en absolu
            seuil_mod_abs = ctx["tolerance_modificateur"] * abs(donnee.valeur_officielle)
            seuil_conf = max(seuil_conf, seuil_mod_abs)
            composantes["modificateur"] = ctx["modificateur"]
            composantes["seuil_modificateur_abs"] = round(seuil_mod_abs, 4)

        # 5. Seuils des verdicts dégradés, en MULTIPLES du seuil confirmé
        #    (justification : un écart de 2× l'arrondi reste explicable ;
        #     au-delà de 5×, l'arrondi ne suffit plus à expliquer)
        seuil_approx = seuil_conf * 2.5
        seuil_imprecis = seuil_conf * 5.0

        # 6. Verdict (en valeur absolue, plus robuste près de zéro que le relatif)
        if ecart_absolu <= seuil_conf:
            verdict = Verdict.CONFIRME
        elif ecart_absolu <= seuil_approx:
            verdict = Verdict.APPROXIMATIF
        elif ecart_absolu <= seuil_imprecis:
            verdict = Verdict.IMPRECIS
        else:
            verdict = Verdict.INCORRECT

        # 7. Atténuation si données provisoires (révision plausible)
        note_prov = ""
        if ctx["est_provisoire"] and verdict in (Verdict.IMPRECIS, Verdict.INCORRECT):
            # On rétrograde d'un cran : un écart sur valeur provisoire est moins grave
            verdict = Verdict.APPROXIMATIF if verdict == Verdict.IMPRECIS else Verdict.IMPRECIS
            note_prov = " (atténué : claim signalé comme provisoire)"

        # 8. Score de confiance
        confiance = self._confiance(ecart_absolu, seuil_conf, seuil_imprecis)

        # 9. Justification traçable
        justif = self._justifier(verdict, claim, donnee, ecart_absolu,
                                 seuil_conf, composantes) + note_prov

        return ResultatValidation(
            claim_id=claim.claim_id,
            verdict=verdict,
            valeur_claim=claim.valeur_claim,
            valeur_officielle=donnee.valeur_officielle,
            ecart_absolu=round(ecart_absolu, 4),
            ecart_relatif=round(ecart_relatif, 4) if ecart_relatif != float('inf') else None,
            seuil_confirme_applique=round(seuil_conf, 4),
            score_confiance=confiance,
            justification=justif,
            composantes_seuil=composantes,
        )

    def _confiance(self, ecart, seuil_conf, seuil_imprecis) -> float:
        """Confiance dans le verdict : forte si l'écart est loin des frontières."""
        if ecart <= seuil_conf:
            # plus l'écart est petit, plus on est sûr du CONFIRME
            ratio = ecart / seuil_conf if seuil_conf else 0
            return round(0.7 + 0.3 * (1 - ratio), 2)
        if ecart >= seuil_imprecis * 2:
            return 0.95  # très loin → INCORRECT certain
        return 0.6  # zone intermédiaire → confiance modérée

    def _justifier(self, verdict, claim, donnee, ecart, seuil, comp) -> str:
        """Construit une justification lisible et traçable."""
        base = (f"Claim {claim.valeur_claim}{claim.unite} vs INSEE "
                f"{donnee.valeur_officielle}{donnee.unite} "
                f"(écart {ecart:.3f}). ")
        seuil_txt = (f"Seuil 'confirmé' = {seuil:.3f} "
                     f"[max(arrondi {comp['arrondi_journalistique']}, "
                     f"IC INSEE {comp['ic_insee']})]. ")
        verdicts_txt = {
            Verdict.CONFIRME: "Écart compatible avec l'arrondi journalistique "
                              "et l'incertitude INSEE → valeur fidèle.",
            Verdict.APPROXIMATIF: "Écart modéré (≤2,5× le seuil), explicable par "
                                  "un arrondi large ou une valeur provisoire.",
            Verdict.IMPRECIS: "Écart notable (≤5× le seuil) : signal faible de "
                              "distorsion, à investiguer qualitativement.",
            Verdict.INCORRECT: "Écart majeur (>5× le seuil) incompatible avec un "
                               "simple arrondi → erreur factuelle probable.",
        }
        return base + seuil_txt + verdicts_txt.get(verdict, "")


# ============================================================================
# TESTS
# ============================================================================

def tests_unitaires():
    print("\n" + "=" * 64)
    print("TESTS UNITAIRES — MODULE 4 RÉVISÉ : VALIDATION")
    print("=" * 64)

    v = Module4Validation()
    erreurs, total = 0, 0

    cas = [
        # (val_claim, brut, indic, unite, val_off, phrase, verdict_attendu, libelle)
        (4.3, "4,3 %", "inflation", "%", 4.28, "l'inflation à 4,3%",
         Verdict.CONFIRME, "Arrondi légitime 4,3 vs 4,28"),
        (7.5, "7,5 %", "chômage", "%", 7.4, "chômage à 7,5%",
         Verdict.CONFIRME, "Chômage 7,5 vs 7,4 (dans IC ±0,3)"),
        (7.5, "7,5 %", "chômage", "%", 7.0, "chômage à 7,5%",
         Verdict.APPROXIMATIF, "Chômage 7,5 vs 7,0 (>IC mais modéré)"),
        (5.5, "5,5 %", "déficit", "%", 5.5, "déficit à 5,5%",
         Verdict.CONFIRME, "Déficit exact"),
        (10.0, "10 %", "inflation", "%", 4.3, "inflation à 10%",
         Verdict.INCORRECT, "Inflation 10 vs 4,3 (erreur majeure)"),
        (4.3, "environ 4 %", "inflation", "%", 4.3, "environ 4%",
         Verdict.CONFIRME, "« environ 4% » vs 4,3 (modificateur)"),
    ]

    for vc, brut, indic, unite, vo, phrase, attendu, libelle in cas:
        total += 1
        claim = ClaimAValider("T", vc, brut, indic, unite, phrase_originale=phrase)
        donnee = DonneeOfficielle(indic, vo, "2023", unite)
        r = v.valider(claim, donnee)
        ok = r.verdict == attendu
        sym = "✅" if ok else "❌"
        if not ok:
            erreurs += 1
        print(f"{sym} {libelle:42s} → {r.verdict.value:13s} (seuil={r.seuil_confirme_applique})")
        if not ok:
            print(f"     Attendu : {attendu.value}")
            print(f"     Justif  : {r.justification}")

    print(f"\nRésultat : {total - erreurs}/{total} tests passés.")
    print("\n⚠️  RAPPEL : les marges IC_INSEE (chômage ±0,3, etc.) doivent être")
    print("    confirmées dans les notes méthodologiques INSEE de chaque indicateur.")
    return erreurs == 0


if __name__ == "__main__":
    tests_unitaires()
