"""Module 0 de bout en bout sur un PDF fictif à la mise en page Europresse.

Le PDF est généré à la volée par `fabrique_pdf.py` (reportlab, dépendance de
développement). Il vérifie le parcours réel : segmentation, métadonnées,
deux colonnes, normalisation du média et troncature au copyright.
"""

import pytest

pytest.importorskip("reportlab")

from fabrique_pdf import fabriquer
from module0_parser_europresse import EuropresseParser


@pytest.fixture(scope="module")
def articles(tmp_path_factory):
    chemin = fabriquer(str(tmp_path_factory.mktemp("pdf") / "export_fictif.pdf"))
    return EuropresseParser().parser(chemin)


def test_segmentation_ignore_la_couverture(articles):
    assert [a.pages_dans_pdf for a in articles] == [[2], [3]]


def test_metadonnees(articles):
    a = articles[0]
    assert a.article_id == "news·20231115·QAL·ex0001"
    assert a.date_publication == "2023-11-15"
    assert a.titre == "Le chômage remonte légèrement cet automne"
    assert a.mots_revendiques == 72


def test_normalisation_du_media(articles):
    assert articles[0].source_media_brut == "Quotidien Alpha"   # « Page 4 » retiré
    assert articles[1].source_media == "AFP"
    assert articles[1].source_media_brut == "AFP - Infos Economiques"


def test_lecture_colonne_gauche_puis_droite(articles):
    texte = articles[0].texte
    assert texte.startswith("Le taux de chômage s'établit à 7,4 % au")
    assert texte.index("Les créations d'emplois") < texte.index("dans l'industrie")
    assert articles[0].taux_extraction == pytest.approx(1.0, abs=0.05)


def test_troncature_au_copyright(articles):
    texte = articles[1].texte
    assert texte.endswith("La prochaine publication est attendue.")
    assert "agrégé par erreur" not in texte
