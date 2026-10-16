"""Fabrique un PDF FICTIF imitant la mise en page d'un export Europresse.

Les exports réels sont sous droits et ne peuvent pas être versionnés. Ce
générateur reproduit seulement ce dont le module 0 a besoin : encart de
métadonnées en petits caractères, identifiant `news·AAAAMMJJ·SOURCE·…`,
titre en grand corps, texte sur deux colonnes, pied de page de copyright.
Médias, titres et textes sont inventés.
"""

from __future__ import annotations

from typing import List

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

LARGEUR, HAUTEUR = A4  # 595 x 842 points


def _texte(c, x, top, chaine, taille, police="Helvetica"):
    """Écrit `chaine` avec son haut de ligne à `top` points du haut de page."""
    c.setFont(police, taille)
    c.drawString(x, HAUTEUR - top - taille * 0.8, chaine)


def _page_article(c, media, date_longue, identifiant, titre, lignes_g, lignes_d,
                  nb_mots, pied_de_page_dans_le_corps: List[str] = ()):
    # Encart de métadonnées (8,2 pt), au-dessus du titre
    top = 60
    for ligne in ("Nom de la source", media, "Type de source", "Presse • Quotidien",
                  "Couverture géographique", "Nationale", "Provenance", "France"):
        _texte(c, 54, top, ligne, 8.2)
        top += 11
    # Bloc de droite placé sur les lignes d'intitulés pour ne pas se mêler aux
    # valeurs (hypothèse de mise en page faite par le module 0)
    _texte(c, 380, 60, date_longue, 8.2)
    _texte(c, 380, 82, f"{nb_mots} mots", 8.2)
    _texte(c, 380, 104, identifiant, 8.2)

    # Titre (18,8 pt) vers y = 186
    _texte(c, 54, 186, titre, 18.8, "Helvetica-Bold")

    # Corps sur deux colonnes (9,8 pt, interligne 12)
    for x, lignes in ((54, lignes_g), (310, lignes_d)):
        top = 230
        for ligne in lignes:
            _texte(c, x, top, ligne, 9.8)
            top += 12
    # Lignes ajoutées sous la colonne de droite (simulation d'agrégation)
    top = 230 + 12 * len(lignes_d)
    for ligne in pied_de_page_dans_le_corps:
        _texte(c, 310, top, ligne, 9.8)
        top += 12

    # Pied de page Europresse (exclu par la marge basse du module 0)
    _texte(c, 54, HAUTEUR - 50, "© 2023 Tous droits réservés.", 7)
    c.showPage()


def fabriquer(chemin: str) -> str:
    """Écrit un PDF de 2 articles fictifs à `chemin` et le renvoie."""
    c = canvas.Canvas(chemin, pagesize=A4)

    # Page de couverture (ignorée par le segmenteur)
    _texte(c, 54, 100, "Documents sauvegardés", 14)
    _texte(c, 54, 130, "Sommaire", 12)
    c.showPage()

    gauche = ["Le taux de chômage s'établit à 7,4 % au",
              "troisième trimestre selon l'Insee. La",
              "hausse reste modérée sur un an et les",
              "économistes jugent la situation stable",
              "malgré le ralentissement de l'activité.",
              "Les créations d'emplois marquent le pas"]
    droite = ["dans l'industrie comme dans les services.",
              "Le gouvernement maintient son objectif",
              "de plein emploi pour la fin du mandat.",
              "Les syndicats demandent des mesures de",
              "soutien ciblées pour les jeunes actifs.",
              "La prochaine publication est attendue."]
    _page_article(c, "Quotidien Alpha Page 4", "Mercredi 15 novembre 2023",
                  "news·20231115·QAL·ex0001", "Le chômage remonte légèrement cet automne",
                  gauche, droite, nb_mots=72)

    # Article de « cahier spécial » : le pied de page de copyright apparaît
    # dans le corps, suivi du début d'un autre article (sur-extraction).
    _page_article(c, "AFP - Infos Economiques", "Jeudi 16 novembre 2023",
                  "news·20231116·AFPD·ex0002", "Inflation : un ralentissement confirmé en octobre",
                  gauche, droite, nb_mots=72,
                  pied_de_page_dans_le_corps=[
                      "© 2023 Agence fictive. Tous droits réservés.",
                      "Un autre article agrégé par erreur commence",
                      "ici et ne doit pas être conservé dans le texte."])
    c.save()
    return chemin
