"""
MODULE 1 : Extraction de Claims Quantitatifs
=============================================

Mémoire de recherche appliquée - INSEEC MSc
Problématique : "Dans quelle mesure peut-on détecter de la désinformation
                 médiatique par la donnée ?"

Ce module identifie dans un texte brut les phrases contenant des données
chiffrées (pourcentages, grands nombres, valeurs monétaires, etc.).

Méthode : Regex patterns optimisés pour le français (virgule décimale,
espaces milliers, unités courantes : %, milliards €, points, etc.)

Entrée  : Texte brut d'un article de presse
Sortie  : Liste de ClaimCandidat (phrase, valeur brute, position)

Auteur : Florian
Date : Février 2026
"""

import re
import logging
from dataclasses import dataclass
from typing import List

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s — %(message)s")
logger = logging.getLogger("Module1")


# ============================================================================
# STRUCTURES DE DONNÉES
# ============================================================================

@dataclass
class ClaimCandidat:
    """
    Claim brut extrait d'un article.
    Sortie du Module 1 → Entrée du Module 2.
    """
    claim_id: str
    phrase: str              # Phrase source contenant le chiffre
    valeur_brute: str        # "7,3%", "2,5 milliards d'euros", etc.
    position_debut: int = 0
    position_fin: int = 0


# ============================================================================
# MODULE 1 : EXTRACTEUR
# ============================================================================

class Module1Extraction:
    """
    Extrait les phrases contenant des données chiffrées.

    Patterns détectés :
      - Pourcentages : 7,3%, 0,9 %, 12.5%
      - Grands nombres : 2,5 milliards, 3 000 millions, 150 mds €
      - Valeurs avec unité : 7,3 points, 1 500 euros
      - Nombres avec espaces milliers : 42 000, 3 000 000

    Limitations connues :
      - Un seul claim par phrase (le premier match)
      - Pas de désambiguïsation (dates vs valeurs)
      - Faux positifs possibles sur les numéros (années, références)
    """

    PATTERNS = [
        # Pourcentages : 7,3%, 0,9 %, 12.5%, -2,1%
        (r'(-?\d+[,\.]\d+)\s*%', "pourcentage_decimal"),
        (r'(-?\d+)\s*%', "pourcentage_entier"),
        # Grands nombres : 2,5 milliards d'euros, 3 000 mds €
        (r'(\d[\d\s]*(?:[,\.]\d+)?)\s*(milliards?|millions?|mds)\s*(d[\'e]\s*euros?|€)?', "grand_nombre"),
        # Valeurs avec unité : 7,3 points, 0,2 point
        (r'(\d+[,\.]\d+)\s*(points?)', "points"),
        # Valeurs monétaires : 1 500 euros, 42 000 €
        (r'(\d[\d\s]*(?:[,\.]\d+)?)\s*(euros?|€)', "monetaire"),
        # Nombres avec espaces milliers : 42 000, 3 000 000
        (r'(\d{1,3}(?:\s\d{3})+)', "grand_entier"),
    ]

    # Mots à exclure (dates, références, numéros de page, etc.)
    EXCLUSIONS = [
        r'article\s+\d+', r'page\s+\d+', r'chapitre\s+\d+',
        r'(?:19|20)\d{2}(?!\s*[%€])',  # Années seules (sauf si suivies de % ou €)
    ]

    def extraire(self, texte: str, article_id: str = "ART") -> List[ClaimCandidat]:
        """
        Extrait les claims candidats d'un texte.

        Args:
            texte: Texte brut de l'article.
            article_id: Identifiant de l'article (pour nommer les claims).

        Returns:
            Liste de ClaimCandidat.
        """
        phrases = self._decouper_phrases(texte)
        claims = []
        idx = 0

        for phrase in phrases:
            phrase_clean = phrase.strip()
            if len(phrase_clean) < 10:
                continue

            for pattern, type_pattern in self.PATTERNS:
                match = re.search(pattern, phrase_clean)
                if match:
                    # Vérifier que ce n'est pas une exclusion
                    if self._est_exclusion(phrase_clean, match):
                        continue
                    idx += 1
                    claims.append(ClaimCandidat(
                        claim_id=f"{article_id}_C{idx:02d}",
                        phrase=phrase_clean,
                        valeur_brute=match.group(0).strip(),
                        position_debut=match.start(),
                        position_fin=match.end(),
                    ))
                    break  # Un seul claim par phrase (le premier trouvé)

        logger.info(f"Module 1 : {len(claims)} claims extraits de {len(phrases)} phrases.")
        return claims

    def _decouper_phrases(self, texte: str) -> List[str]:
        """Découpe un texte en phrases."""
        # Split sur ponctuation de fin de phrase
        phrases = re.split(r'(?<=[.!?])\s+', texte)
        # Gestion des retours à la ligne
        result = []
        for p in phrases:
            sub = p.split('\n')
            result.extend(s.strip() for s in sub if s.strip())
        return result

    def _est_exclusion(self, phrase: str, match) -> bool:
        """Vérifie si le match est un faux positif connu."""
        contexte = phrase[max(0, match.start()-20):match.end()+20].lower()
        for excl in self.EXCLUSIONS:
            if re.search(excl, contexte):
                return True
        return False


# ============================================================================
# TESTS UNITAIRES
# ============================================================================

def tests_unitaires():
    print("\n" + "=" * 60)
    print("TESTS UNITAIRES — MODULE 1 : EXTRACTION")
    print("=" * 60)

    m1 = Module1Extraction()
    erreurs, total = 0, 0

    # Test 1 : Pourcentages
    total += 1
    claims = m1.extraire("Le chômage recule à 7,3% au T4. L'inflation est à 3,7%.", "T1")
    if len(claims) == 2:
        print(f"✅ Test 1 : 2 pourcentages extraits — {[c.valeur_brute for c in claims]}")
    else:
        print(f"❌ Test 1 : Attendu 2, obtenu {len(claims)}")
        erreurs += 1

    # Test 2 : Grands nombres
    total += 1
    claims = m1.extraire("La dette atteint 3 000 milliards d'euros.", "T2")
    if len(claims) >= 1 and "milliard" in claims[0].valeur_brute.lower():
        print(f"✅ Test 2 : Grand nombre extrait — '{claims[0].valeur_brute}'")
    else:
        print(f"❌ Test 2 : Extraction grand nombre échouée")
        erreurs += 1

    # Test 3 : Texte sans chiffre
    total += 1
    claims = m1.extraire("La situation économique reste incertaine.", "T3")
    if len(claims) == 0:
        print(f"✅ Test 3 : Aucun claim dans texte sans chiffre")
    else:
        print(f"❌ Test 3 : {len(claims)} faux positif(s)")
        erreurs += 1

    # Test 4 : Article réaliste
    total += 1
    texte = """Le taux de chômage s'établit à 7,3% au quatrième trimestre 2023.
    L'inflation recule à 3,7% en décembre. Le PIB progresse de 0,9% en 2023.
    La dette publique dépasse 3 000 milliards d'euros. Le gouvernement
    prévoit une croissance de 1,4% en 2024."""
    claims = m1.extraire(texte, "T4")
    if len(claims) >= 4:
        print(f"✅ Test 4 : Article réaliste → {len(claims)} claims")
        for c in claims:
            print(f"       {c.claim_id}: '{c.valeur_brute}'")
    else:
        print(f"❌ Test 4 : Attendu ≥4, obtenu {len(claims)}")
        erreurs += 1

    print(f"\nRésultat : {total - erreurs}/{total} tests passés.")
    return erreurs == 0


if __name__ == "__main__":
    tests_unitaires()
