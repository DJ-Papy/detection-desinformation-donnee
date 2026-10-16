"""Module 1.5 — classification en régimes de vérifiabilité (version 2)."""

import pytest

from module1_5_classifieur_regime import ClassifieurRegime, Regime

CLF = ClassifieurRegime()
R1, R2, IND = Regime.FORTE, Regime.FAIBLE, Regime.INDETERMINE


# --- Cas de la version 1, toujours valides en version 2 --------------------
@pytest.mark.parametrize("phrase, ind_m2, unite, attendu", [
    ("L'inflation s'établit à 4,3% sur un an en juillet, selon l'Insee.", "inflation", "%", R1),
    ("Le taux de chômage atteint 7,5% au quatrième trimestre, indique l'Insee.", "chômage", "%", R1),
    ("L'objectif est de 20 milliards d'euros d'économies pour 2025.", "", "milliards €", R2),
    ("Le déficit des hôpitaux s'élève à 1,7 milliard d'euros pour 2023.", "", "milliards €", R2),
    ("Le PIB a progressé de 0,2% au deuxième trimestre, selon l'Insee.", "PIB", "%", R1),
    ("Le gouvernement prévoit une croissance de 1,4% en 2024.", "PIB", "%", R2),
    ("Ces dernières devront s'élever à 20 milliards d'euros.", "", "milliards €", R2),
    ("La dette publique a reculé à 111,8% du PIB, selon l'Insee.", "dette", "%", R1),
])
def test_cas_v1(phrase, ind_m2, unite, attendu):
    assert CLF.classer("T", phrase, indicateur_m2=ind_m2, unite_m2=unite).regime == attendu


# --- Règles propres à la version 2 (§2.4.1) --------------------------------
def test_condition_necessaire_pas_de_regime_1_sans_indicateur():
    # v1 : « % » (+0,5) + verbe de constat (+1) suffisaient pour le régime 1
    res = CLF.classer("T", "Le taux d'épargne atteint 17,5 %.", unite_m2="%")
    assert res.regime == IND
    assert "condition nécessaire" in res.justification


def test_exclusion_pays_etranger():
    res = CLF.classer("T", "L'inflation en Espagne s'établit à 2,4 % en juin 2024.",
                      unite_m2="%", date_article="2024-07-01")
    assert res.regime == R2


def test_pays_etranger_avec_marqueur_francais_non_exclu():
    res = CLF.classer("T", "En France, l'inflation (2,3 %) reste inférieure à celle "
                      "de l'Allemagne, selon l'Insee.", unite_m2="%")
    assert res.regime == R1


def test_exclusion_annee_future():
    res = CLF.classer("T", "La dette publique atteindra 3 200 milliards d'euros fin 2025.",
                      date_article="2024-06-01")
    assert res.regime == R2
    assert "année postérieure" in res.justification


def test_annee_future_necessite_la_date_article():
    # Sans date d'article, l'exclusion n'est pas appliquée. Le futur simple
    # « atteindra » n'étant pas un marqueur de prévision (seul « atteindre »
    # l'est, cf. L3), la phrase bascule alors à tort en régime 1 : d'où
    # l'importance de toujours transmettre date_article.
    phrase = "La dette publique atteindra 3 200 milliards d'euros fin 2025."
    assert CLF.classer("T", phrase).regime == R1
    assert CLF.classer("T", phrase, date_article="2024-06-01").regime == R2


def test_exclusion_ratio_pib_renvoie_a_la_dette():
    res = CLF.classer("T", "La dette publique a représenté 110,6 % du PIB en 2023.",
                      unite_m2="%", date_article="2024-03-26")
    assert res.regime == R1
    assert res.indicateur_officiel == "dette"   # v1 : « PIB »


def test_croissance_du_pib_n_est_pas_un_ratio():
    res = CLF.classer("T", "La croissance du PIB atteint 0,9 % en 2023, selon l'Insee.",
                      unite_m2="%", date_article="2024-01-31")
    assert (res.regime, res.indicateur_officiel) == (R1, "PIB")


# --- Exemples du guide de codage (Annexe 3 du mémoire) ---------------------
# Le guide décrit le JUGEMENT HUMAIN attendu, pas le comportement du code :
# les écarts sont précisément ce que le protocole de validation (κ de Cohen,
# §2.4.2) doit mesurer. Deux exemples divergent ; ils sont documentés dans
# docs/limites_connues.md (D1, D2).
@pytest.mark.parametrize("phrase, guide, code", [
    ("Le taux de chômage s'établit à 7,3 % au quatrième trimestre 2023 selon l'INSEE.", R1, R1),
    ("Le gouvernement vise un déficit ramené à 4,4 % du PIB en 2027.", R2, R2),
    ("Selon les projections de Bercy, la dette publique atteindra 3 200 milliards "
     "d'euros fin 2025.", R2, R2),
    ("Le PIB français a progressé de 0,9 % en 2023.", R1, R1),
    ("Un rapport chiffre à environ 15 milliards d'euros le coût pour les finances "
     "publiques.", IND, R2),                                     # divergence D1
    ("L'inflation en Espagne s'établit à 2,4 % en juin 2024.", R2, R2),
    ("L'objectif est de créer 300 000 emplois d'ici 2027.", R2, R2),
    ("Les prix à la consommation ont augmenté de 4,9 % en moyenne annuelle en 2023 "
     "(INSEE).", R1, R1),
    ("Le déficit public a représenté 5,5 % du PIB en 2023.", IND, R1),  # divergence D2
])
def test_exemples_annexe_3(phrase, guide, code):
    res = CLF.classer("T", phrase, unite_m2="%" if "%" in phrase else "",
                      date_article="2024-06-01")
    assert res.regime == code


@pytest.mark.xfail(strict=True, reason="L3 : marqueurs cherchés comme sous-chaînes ; "
                   "« demandeurs » contient « demande » (marqueur de prévision)")
def test_L3_sous_chaine_demande_dans_demandeurs():
    res = CLF.classer("T", "Le taux de chômage atteint 7,4 %, mais on compte 3 millions "
                      "de demandeurs d'emploi selon l'Insee.", unite_m2="%")
    assert res.regime == R1
