"""Module 2 — structuration (valeur, unité, indicateur, période)."""

import pytest

from module2_structuration import ClaimCandidat, Module2Structuration

M2 = Module2Structuration()


def structurer(phrase, brut, date=""):
    return M2.structurer([ClaimCandidat("T", phrase, brut)], date)[0]


def test_pourcentage_chomage_trimestre_textuel():
    s = structurer("Le chômage recule à 7,3% au quatrième trimestre 2023.", "7,3%", "2024-02-15")
    assert (s.valeur, s.unite, s.indicateur, s.periode) == (7.3, "%", "chômage", "2023-Q4")


def test_grand_nombre_dette():
    s = structurer("La dette dépasse 3 000 milliards d'euros.", "3 000 milliards d'euros")
    assert (s.valeur, s.unite, s.indicateur) == (3000.0, "milliards €", "dette")


def test_modificateur():
    assert structurer("Le PIB progresse d'environ 0,9% en 2023.", "0,9%").modificateur == "environ"


def test_mois():
    assert structurer("L'inflation atteint 3,7% en décembre 2023.", "3,7%", "2024-02-15").periode == "2023-12"


def test_effectif_n_est_pas_un_taux():
    assert structurer("On compte 64 000 chômeurs de plus.", "64 000").unite == "effectif"


def test_repli_sur_l_annee_de_l_article():
    # Limite reconnue par le mémoire (§2.3.2) : sans mention explicite, la
    # période est héritée de la date de l'article, sans le signaler.
    assert structurer("Le taux de chômage s'établit à 7,4 %.", "7,4 %", "2024-02-13").periode == "2024"


@pytest.mark.xfail(strict=True, reason="L4 : les mois sont cherchés comme sous-"
                   "chaînes ; « semaine » contient « mai » → période AAAA-05")
def test_L4_mai_dans_semaine():
    s = structurer("Cette semaine, l'inflation ressort à 4,3 %.", "4,3 %", "2023-07-28")
    assert s.periode == "2023"


@pytest.mark.xfail(strict=True, reason="L5 : « la hausse des prix » (définition "
                   "même de l'inflation) fait classer le claim comme variation")
def test_L5_hausse_des_prix_n_est_pas_une_variation():
    s = structurer("La hausse des prix à la consommation s'établit à 4,3 % sur un an.", "4,3 %")
    assert s.est_variation is False
