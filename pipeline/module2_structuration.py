"""
MODULE 2 : Structuration des Claims Quantitatifs
==================================================

Mémoire de recherche appliquée - INSEEC MSc
Problématique : "Dans quelle mesure peut-on détecter de la désinformation
                 médiatique par la donnée ?"

Ce module transforme les claims bruts (Module 1) en structures exploitables
pour la vérification via l'API INSEE (Module 3).

Opérations :
  1. Parsing numérique (virgule → point, gestion milliards/millions)
  2. Détection d'unité (%, milliards €, points, etc.)
  3. Identification de l'indicateur (chômage, PIB, inflation, dette, etc.)
  4. Résolution temporelle (trimestres, mois, années)
  5. Détection de modificateurs ("environ", "près de", "plus de")

Point méthodologique clé : la résolution temporelle par valeur associe
chaque chiffre à la référence temporelle la plus proche dans la phrase.

Entrée  : Liste de ClaimCandidat (Module 1)
Sortie  : Liste de ClaimStructure (claim_id, valeur, unité, indicateur, période)

Auteur : Florian
Date : Février 2026
"""

import re
import logging
from dataclasses import dataclass
from typing import List, Optional, Dict

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s — %(message)s")
logger = logging.getLogger("Module2")


# ============================================================================
# STRUCTURES DE DONNÉES
# ============================================================================

@dataclass
class ClaimCandidat:
    """Entrée : sortie du Module 1."""
    claim_id: str
    phrase: str
    valeur_brute: str
    position_debut: int = 0
    position_fin: int = 0

@dataclass
class ClaimStructure:
    """
    Sortie du Module 2 → Entrée du Module 3.

    Claim structuré avec toutes les métadonnées nécessaires
    pour interroger l'API INSEE.
    """
    claim_id: str
    phrase_originale: str
    valeur: float
    unite: str               # "%", "milliards €", "millions", "points"
    indicateur: str           # "chômage", "PIB", "inflation", "dette", "population"
    periode: str              # "2023-Q4", "2023-12", "2023"
    modificateur: str = ""    # "environ", "près de", "plus de"
    contexte_phrase: str = ""
    est_variation: bool = False  # True si claim porte sur une variation


# ============================================================================
# MODULE 2 : STRUCTURATEUR
# ============================================================================

class Module2Structuration:
    """
    Transforme les claims bruts en structures exploitables.
    """

    INDICATEURS_KEYWORDS = {
        "chômage": ["chômage", "chômeuse", "chômeurs", "demandeurs d'emploi",
                     "taux de chômage", "sans emploi", "emploi"],
        "PIB": ["pib", "produit intérieur brut", "croissance", "récession",
                "croissance économique", "activité économique"],
        "inflation": ["inflation", "prix à la consommation", "ipc",
                      "hausse des prix", "coût de la vie", "déflation"],
        "dette": ["dette", "endettement", "déficit", "dette publique",
                  "déficit public", "déficit budgétaire"],
        "population": ["population", "habitants", "démographie", "immigr",
                       "natalité", "espérance de vie"],
        "salaire": ["salaire", "smic", "rémunération", "pouvoir d'achat",
                    "revenu", "salaire moyen", "salaire médian"],
    }

    MOIS = {
        "janvier":"01","février":"02","mars":"03","avril":"04",
        "mai":"05","juin":"06","juillet":"07","août":"08",
        "septembre":"09","octobre":"10","novembre":"11","décembre":"12",
    }

    TRIMESTRES_TEXTE = {
        "premier":"1","deuxième":"2","troisième":"3","quatrième":"4",
        "1er":"1","2e":"2","2ème":"2","3e":"3","3ème":"3","4e":"4","4ème":"4",
    }

    MODIFICATEURS = ["environ", "près de", "plus de", "moins de",
                     "autour de", "presque", "quasi", "à peine"]

    MOTS_VARIATION = ["hausse", "baisse", "recul", "progression", "augmentation",
                      "diminution", "repli", "bond", "chute", "gain", "perte",
                      "en hausse", "en baisse", "en recul", "en progression"]

    def structurer(self, candidats: List[ClaimCandidat],
                   date_article: str = "") -> List[ClaimStructure]:
        """
        Transforme une liste de claims bruts en claims structurés.

        Args:
            candidats: Claims bruts du Module 1.
            date_article: Date de publication (format YYYY-MM-DD), pour fallback temporel.

        Returns:
            Liste de ClaimStructure.
        """
        resultats = []
        for c in candidats:
            valeur = self._parser_valeur(c.valeur_brute)
            if valeur is None:
                logger.debug(f"Valeur non parsable : '{c.valeur_brute}'")
                continue

            unite = self._detecter_unite(c.valeur_brute, c.phrase)
            indicateur = self._detecter_indicateur(c.phrase)
            periode = self._detecter_periode(c.phrase, date_article)
            modificateur = self._detecter_modificateur(c.phrase)
            est_variation = self._est_variation(c.phrase)

            resultats.append(ClaimStructure(
                claim_id=c.claim_id,
                phrase_originale=c.phrase,
                valeur=valeur,
                unite=unite,
                indicateur=indicateur,
                periode=periode,
                modificateur=modificateur,
                contexte_phrase=c.phrase,
                est_variation=est_variation,
            ))

        logger.info(f"Module 2 : {len(resultats)}/{len(candidats)} claims structurés.")
        return resultats

    def _parser_valeur(self, brut: str) -> Optional[float]:
        """Parse une valeur brute en float."""
        nettoye = re.sub(r'[%€]', '', brut).strip()
        nettoye = re.sub(r'\s*(milliards?|millions?|mds|points?|euros?)\s*', '',
                         nettoye, flags=re.I)
        nettoye = re.sub(r"d['\s]", '', nettoye)
        nettoye = nettoye.replace('\xa0', '').replace(' ', '').replace(',', '.')
        try:
            val = float(nettoye)
            # Multiplicateur
            brut_l = brut.lower()
            if 'milliard' in brut_l or 'mds' in brut_l:
                pass  # On garde la valeur en milliards (unité = "milliards €")
            if 'million' in brut_l:
                pass  # Idem
            return val
        except ValueError:
            return None

    def _detecter_unite(self, brut: str, phrase: str) -> str:
        b = brut.lower()
        # Unités explicites dans la valeur brute
        if '%' in b: return "%"
        if 'milliard' in b or 'mds' in b: return "milliards €"
        if 'million' in b: return "millions"
        if 'point' in b: return "points"
        if '€' in b or 'euro' in b: return "€"

        # Détecter un VOLUME (nombre de personnes/emplois/postes) : ce n'est PAS
        # un taux, même près d'un mot économique. Ex : "64 000 chômeurs".
        val = self._parser_valeur(brut)
        contexte = phrase.lower()
        marqueurs_volume = ["chômeur", "chomeur", "emploi", "poste", "personne",
                            "salarié", "demandeur", "actif", "habitant",
                            "création", "destruction", "suppression"]
        # Un grand entier (≥ 1000) est presque toujours un volume, pas un taux
        if val is not None and abs(val) >= 1000:
            return "effectif"
        # Un nombre suivi/précédé d'un marqueur de volume = effectif
        if any(m in contexte for m in marqueurs_volume) and '%' not in brut:
            # mais seulement si le % n'est pas explicitement attaché au nombre
            # (ex : "le chômage à 7,4%" garde le %, "64 000 chômeurs" → effectif)
            if not re.search(r'\d+(?:[.,]\d+)?\s*%', brut):
                return "effectif"

        # Inférer % seulement si présent dans la phrase ET pas de marqueur volume
        if '%' in phrase:
            return "%"
        # Plus de "%" par défaut aveugle : on signale l'indétermination
        return "indéterminée"

    def _detecter_indicateur(self, phrase: str) -> str:
        p = phrase.lower()
        scores = {}
        for indic, kws in self.INDICATEURS_KEYWORDS.items():
            score = sum(1 for kw in kws if kw in p)
            if score > 0:
                scores[indic] = score
        if scores:
            return max(scores, key=scores.get)
        return "inconnu"

    def _detecter_periode(self, phrase: str, date_article: str) -> str:
        p = phrase.lower()

        # Trimestres numériques : T4 2023, 4e trimestre 2023
        m = re.search(r'(?:au\s+)?(\d)[eè](?:me)?\s*trimestre\s+(\d{4})', p)
        if m: return f"{m.group(2)}-Q{m.group(1)}"
        m = re.search(r't(\d)\s+(\d{4})', p)
        if m: return f"{m.group(2)}-Q{m.group(1)}"

        # Trimestres textuels : quatrième trimestre 2023
        for txt, num in self.TRIMESTRES_TEXTE.items():
            m = re.search(rf'{txt}\s+trimestre\s+(\d{{4}})', p)
            if m: return f"{m.group(1)}-Q{num}"

        # Mois : en décembre 2023, décembre 2023
        for mois_nom, mois_num in self.MOIS.items():
            if mois_nom in p:
                m2 = re.search(r'(\d{4})', p)
                annee = m2.group(1) if m2 else (date_article[:4] if date_article else "")
                if annee: return f"{annee}-{mois_num}"

        # Année seule : en 2023, sur 2023
        m = re.search(r'\b(20\d{2})\b', p)
        if m: return m.group(1)

        # Fallback : année de l'article
        return date_article[:4] if date_article else "inconnu"

    def _detecter_modificateur(self, phrase: str) -> str:
        p = phrase.lower()
        for mod in self.MODIFICATEURS:
            if mod in p:
                return mod
        return ""

    def _est_variation(self, phrase: str) -> bool:
        p = phrase.lower()
        return any(mot in p for mot in self.MOTS_VARIATION)


# ============================================================================
# TESTS UNITAIRES
# ============================================================================

def tests_unitaires():
    print("\n" + "=" * 60)
    print("TESTS UNITAIRES — MODULE 2 : STRUCTURATION")
    print("=" * 60)

    m2 = Module2Structuration()
    erreurs, total = 0, 0

    # Test 1 : Parsing pourcentage
    total += 1
    candidats = [ClaimCandidat("T1", "Le chômage recule à 7,3% au quatrième trimestre 2023.", "7,3%")]
    res = m2.structurer(candidats, "2024-02-15")
    if res and res[0].valeur == 7.3 and res[0].unite == "%" and res[0].indicateur == "chômage":
        print(f"✅ Test 1 : 7,3% chômage → val={res[0].valeur}, ind={res[0].indicateur}, per={res[0].periode}")
    else:
        print(f"❌ Test 1 : Structuration échouée")
        erreurs += 1

    # Test 2 : Résolution trimestre textuel
    total += 1
    if res and res[0].periode == "2023-Q4":
        print(f"✅ Test 2 : 'quatrième trimestre 2023' → {res[0].periode}")
    else:
        print(f"❌ Test 2 : Période incorrecte : {res[0].periode if res else 'N/A'}")
        erreurs += 1

    # Test 3 : Grand nombre
    total += 1
    candidats = [ClaimCandidat("T3", "La dette dépasse 3 000 milliards d'euros.", "3 000 milliards d'euros")]
    res = m2.structurer(candidats)
    if res and res[0].unite == "milliards €" and res[0].indicateur == "dette":
        print(f"✅ Test 3 : Grand nombre → val={res[0].valeur}, unite={res[0].unite}")
    else:
        print(f"❌ Test 3 : Grand nombre échoué")
        erreurs += 1

    # Test 4 : Modificateur
    total += 1
    candidats = [ClaimCandidat("T4", "Le PIB progresse d'environ 0,9% en 2023.", "0,9%")]
    res = m2.structurer(candidats, "2024-01-01")
    if res and res[0].modificateur == "environ":
        print(f"✅ Test 4 : Modificateur détecté : '{res[0].modificateur}'")
    else:
        print(f"❌ Test 4 : Modificateur non détecté")
        erreurs += 1

    # Test 5 : Mois
    total += 1
    candidats = [ClaimCandidat("T5", "L'inflation atteint 3,7% en décembre 2023.", "3,7%")]
    res = m2.structurer(candidats, "2024-02-15")
    if res and res[0].periode == "2023-12":
        print(f"✅ Test 5 : Mois → {res[0].periode}")
    else:
        print(f"❌ Test 5 : Période mois incorrecte : {res[0].periode if res else 'N/A'}")
        erreurs += 1

    print(f"\nRésultat : {total - erreurs}/{total} tests passés.")
    return erreurs == 0


if __name__ == "__main__":
    tests_unitaires()
