"""Module 5 — cadrage inter-médias (mesure de sélection, marqueurs Entman)."""

import pytest

from module5_cadrage import ArticleCadrage, Module5Cadrage

M5 = Module5Cadrage()


def article(i, media, chiffres, texte="Le déficit public se creuse."):
    return ArticleCadrage(i, media, "titre", texte, "2024-03-27", chiffres)


def test_selections_identiques_divergence_nulle():
    a = M5.analyser_evenement("e", [article("1", "A", ["5,5 %"]), article("2", "B", ["5,5%"])],
                              mots_cles_evenement=["déficit"])
    assert a.indice_divergence == 0.0 and a.chiffres_consensuels == ["5.5%"]


def test_selections_disjointes_divergence_maximale():
    a = M5.analyser_evenement("e", [article("1", "A", ["5,5 %"]), article("2", "B", ["10 milliards"])],
                              mots_cles_evenement=["déficit"])
    assert a.indice_divergence == 1.0 and a.chiffres_consensuels == []


def test_indice_de_divergence_definition():
    # univers = {5.5%, 110.6%, 10Md, 42Md} ; exclusifs = {10Md, 42Md} → 2/4
    arts = [article("1", "A", ["5,5 %", "110,6 %", "10 milliards"]),
            article("2", "B", ["5,5 %", "110,6 %", "42 milliards"])]
    assert M5.analyser_evenement("e", arts, ["déficit"]).indice_divergence == 0.5


def test_filtre_de_pertinence():
    arts = [article("1", "A", ["5,5 %"]),
            article("2", "B", ["85 %"], texte="Un témoignage sur la fin de vie.")]
    a = M5.analyser_evenement("e", arts, mots_cles_evenement=["déficit"])
    assert (a.n_articles, a.n_pertinents) == (2, 1)


@pytest.mark.parametrize("texte, fonction, attendu", [
    ("Le gouvernement doit réagir.", "jugement_moral", 1),
    ("Le droit du travail évolue.", "jugement_moral", 0),        # « doit » ⊄ « droit »
    ("Un plan de relance est annoncé.", "remede", 1),
    ("La planète se réchauffe.", "remede", 0),                    # « plan » ⊄ « planète »
    ("La hausse s'explique par la baisse des recettes.", "attribution_causale", 1),
])
def test_marqueurs_entman_en_mot_entier(texte, fonction, attendu):
    assert M5._scorer_entman(texte)[fonction] == attendu
