"""Module 4 — verdict de véracité (seuils : arrondi journalistique et IC INSEE)."""

import pytest

from module4_validation_revise import (
    ClaimAValider, DonneeOfficielle, Module4Validation, SeuilsJustifies, Verdict)

M4 = Module4Validation()


@pytest.mark.parametrize("valeur, brut, indic, officielle, phrase, attendu", [
    (4.3, "4,3 %", "inflation", 4.28, "l'inflation à 4,3%", Verdict.CONFIRME),
    (7.5, "7,5 %", "chômage", 7.4, "chômage à 7,5%", Verdict.CONFIRME),      # dans l'IC ±0,3
    (7.5, "7,5 %", "chômage", 7.0, "chômage à 7,5%", Verdict.APPROXIMATIF),
    (5.5, "5,5 %", "déficit", 5.5, "déficit à 5,5%", Verdict.CONFIRME),
    (10.0, "10 %", "inflation", 4.3, "inflation à 10%", Verdict.INCORRECT),
    (4.3, "environ 4 %", "inflation", 4.3, "environ 4%", Verdict.CONFIRME),  # modificateur
])
def test_verdicts(valeur, brut, indic, officielle, phrase, attendu):
    claim = ClaimAValider("T", valeur, brut, indic, "%", phrase_originale=phrase)
    assert M4.valider(claim, DonneeOfficielle(indic, officielle, "2023", "%")).verdict == attendu


def test_donnee_manquante_indeterminee():
    claim = ClaimAValider("T", 7.5, "7,5 %", "chômage", "%")
    res = M4.valider(claim, DonneeOfficielle("chômage", None, "2023-Q4", "%", trouve=False))
    assert res.verdict == Verdict.INDETERMINE


@pytest.mark.parametrize("brut, tolerance", [("4,3%", 0.05), ("4,28%", 0.005), ("5%", 0.5)])
def test_precision_arrondi(brut, tolerance):
    assert SeuilsJustifies.precision_arrondi(brut) == pytest.approx(tolerance)


def test_valeur_provisoire_attenue_le_verdict():
    claim = ClaimAValider("T", 5.0, "5,0 %", "inflation", "%",
                          phrase_originale="selon l'estimation flash, l'inflation à 5,0 %")
    res = M4.valider(claim, DonneeOfficielle("inflation", 4.3, "2023-07", "%"))
    assert res.verdict == Verdict.IMPRECIS  # INCORRECT atténué d'un cran
