"""Module 1 — extraction des affirmations chiffrées.

Les tests marqués `xfail` décrivent des limites CONNUES (docs/limites_connues.md).
Ils échouent volontairement : le comportement est conservé tel quel parce que
c'est celui qui a produit les résultats du mémoire. Le jour où une limite est
corrigée, le test passe et pytest le signale (strict=True).
"""

import pytest

from module1_extraction import Module1Extraction

M1 = Module1Extraction()


def valeurs(texte):
    return [c.valeur_brute for c in M1.extraire(texte, "T")]


def test_pourcentages():
    assert valeurs("Le chômage recule à 7,3% au T4. L'inflation est à 3,7%.") == ["7,3%", "3,7%"]


def test_grand_nombre():
    assert "milliard" in valeurs("La dette atteint 3 000 milliards d'euros.")[0]


def test_texte_sans_chiffre():
    assert valeurs("La situation économique reste incertaine.") == []


def test_un_seul_claim_par_phrase():
    # Choix assumé (§2.3.1) : le premier motif pertinent de la phrase
    assert valeurs("L'inflation passe de 3,7 % à 2,4 % en six mois.") == ["3,7 %"]


@pytest.mark.xfail(strict=True, reason="L1 : un chiffre suivi d'une année à "
                   "moins de 20 caractères est écarté comme s'il était une date")
def test_L1_chiffre_suivi_d_une_annee():
    assert valeurs("Le PIB progresse de 0,9% en 2023.") == ["0,9%"]


@pytest.mark.xfail(strict=True, reason="L2 : un retour à la ligne est traité "
                   "comme une fin de phrase (lignes de colonnes Europresse)")
def test_L2_retour_a_la_ligne_dans_une_phrase():
    claims = M1.extraire("Le gouvernement\nprévoit une croissance de 1,4 %.", "T")
    assert claims[0].phrase.startswith("Le gouvernement")
