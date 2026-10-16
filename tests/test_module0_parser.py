"""Module 0 — fonctions de parsing testables sans PDF Europresse.

Le parcours complet d'un PDF est testé dans test_module0_pdf.py, sur un
PDF fictif généré à la volée : les exports Europresse réels sont sous droits
et ne peuvent pas être versionnés. Pour vérifier le parser sur vos propres
exports : `python pipeline/module0_parser_europresse.py export.pdf` (mode
diagnostic, avec contrôle du nombre de mots).
"""

import pytest

from module0_parser_europresse import (
    EuropresseBodyExtractor, EuropresseMetadataExtractor, normaliser_media)


@pytest.mark.parametrize("brut, attendu", [
    ("AFP - Infos Economiques", "AFP"),
    ("Le Monde Page", "Le Monde"),          # parasite de vignette
    ("Les Echos", "Les Échos"),              # sans accent dans l'export
    ("L’Obs", "L'Obs"),                      # apostrophe typographique
    ("Libération", "Libération"),
    ("Rubrique Économie", "Rubrique Économie"),  # inconnu → inchangé
])
def test_normaliser_media(brut, attendu):
    assert normaliser_media(brut) == attendu


def test_normaliser_media_repli_sur_code_source():
    # La métadonnée a capté une rubrique : repli sur le code de l'identifiant
    assert normaliser_media("Économie", "news·20230728·AFPD·tx-par-blw82") == "AFP"


def test_troncature_au_copyright():
    texte = ("Premier article, dernier paragraphe.\n"
             "© 2023 Le Monde. Tous droits réservés.\n"
             "Titre de l'article suivant agrégé par erreur")
    assert EuropresseBodyExtractor().tronquer_fin_article(texte) == \
        "Premier article, dernier paragraphe."


def test_troncature_sans_marqueur_ne_change_rien():
    texte = "Un article sans pied de page."
    assert EuropresseBodyExtractor().tronquer_fin_article(texte) == texte


def test_nettoyage_recolle_les_cesures():
    brut = "la consomma-\ntion des ménages"
    assert EuropresseBodyExtractor()._nettoyer(brut) == "la consommation des ménages"


def test_dates():
    meta = EuropresseMetadataExtractor()
    assert meta._date_iso_depuis_id("20230728") == "2023-07-28"
    assert meta._extraire_date("Vendredi 28 juillet 2023") == \
        ("Vendredi 28 juillet 2023", "2023-07-28")
    assert meta._nettoyer_valeur_meta("Le Monde 9") == "Le Monde"
