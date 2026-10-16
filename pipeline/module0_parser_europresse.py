"""
MODULE 0 : Parser PDF Europresse
=================================

Mémoire INSEEC MSc — Data & Marketing Digital — 2025-2026
Problématique : "Dans quelle mesure peut-on détecter de la désinformation
                 médiatique par la donnée ?"

Ce module convertit un export PDF Europresse (Cision/CEDROM-SNi) en une
liste structurée d'articles exploitables par le pipeline (M1 → M5).

Stratégie d'extraction :
  1. Identification des pages d'articles via le titre H1 (taille ~18.8pt)
  2. Regroupement page principale + continuations
  3. Extraction de l'encart métadonnées (zone haute, à gauche du titre)
  4. Extraction du corps en 2 colonnes (détection automatique des bornes X)
  5. Nettoyage typographique (recollage césures, espaces collés)
  6. Validation par checksum (mot count Europresse vs notre extraction)

Architecture modulaire :
  - `EuropressePagePattern` : détection des seuils typographiques
  - `EuropresseArticleSegmenter` : segmentation pages → articles
  - `EuropresseMetadataExtractor` : parsing de l'encart métadonnées
  - `EuropresseBodyExtractor` : extraction du corps avec gestion 2-colonnes
  - `EuropresseParser` : orchestrateur

Cette architecture permet de remplacer un sous-module si le format Europresse
évolue ou si on traite un autre fournisseur (Factiva, LexisNexis).

VERSION 2 — corrections décrites au §2.2.2 du mémoire (reconstruites)
  - Sur-extraction : sur certains cahiers spéciaux, le segmenteur ne voyait
    pas la frontière de l'article suivant et agrégeait plusieurs articles
    (jusqu'à 718 % du nombre de mots attendu). Le corps est désormais tronqué
    à la première mention de copyright Europresse, marqueur de fin d'article
    (`EuropressePagePattern.REGEX_FIN_ARTICLE`).
  - Métadonnée « média » : certains articles portaient un intitulé de rubrique
    au lieu du nom du titre. Le nom est désormais normalisé
    (`normaliser_media`), la valeur brute est conservée dans
    `source_media_brut`.
  ⚠️ Le code exact de ces corrections n'a pas été conservé ; il est réécrit
  d'après le mémoire. Les marqueurs de fin d'article sont ceux du pied de page
  Europresse usuel : à vérifier sur vos propres exports.

Auteur : Florian, mai 2026 (v2 reconstruite en octobre 2026).
"""

from __future__ import annotations
import re
import logging
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import List, Optional, Dict, Tuple, Any
from collections import Counter

try:
    import pdfplumber
except ImportError:
    raise ImportError(
        "pdfplumber est requis. Installation : pip install pdfplumber"
    )

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
logger = logging.getLogger("Module0")


# ============================================================================
# STRUCTURES DE DONNÉES
# ============================================================================

@dataclass
class ArticleEuropresse:
    """
    Article extrait d'un PDF Europresse.

    Cette structure correspond exactement à `ArticleInput` du pipeline aval
    (M1 → M5), avec en plus les métadonnées Europresse natives.
    """

    # Identifiants
    article_id: str                    # ID Europresse natif (news·20230728·AFPD·...)
    source_pdf: str                    # Nom du fichier PDF d'origine
    pages_dans_pdf: List[int]          # Pages où l'article apparaît (1-indexed)

    # Métadonnées éditoriales
    source_media: str                  # "AFP - Infos Economiques", "Le Monde", etc.
    type_source: str                   # "Presse • Fils de presse", "Presse • Quotidien"
    couverture_geographique: str       # "Internationale", "Nationale", "Régionale"
    provenance: str                    # "France", "Belgique", etc.
    date_publication: str              # Format ISO YYYY-MM-DD
    date_publication_raw: str          # Format brut Europresse ("Vendredi 28 juillet 2023")

    # Contenu
    titre: str                         # Titre H1 nettoyé
    texte: str                         # Corps de l'article nettoyé
    mots_revendiques: int              # "311 mots" annoncé par Europresse
    mots_extraits: int                 # Notre comptage après extraction

    # Champs utilisés en aval par le pipeline
    sujet: str = ""                    # À renseigner manuellement ou via M5

    # v2 : nom du média tel que lu dans l'encart, avant normalisation
    source_media_brut: str = ""

    # Diagnostics
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Export pour CSV/JSON."""
        return asdict(self)

    @property
    def taux_extraction(self) -> float:
        """Ratio mots extraits / mots revendiqués (proche de 1.0 = OK)."""
        if self.mots_revendiques == 0:
            return 0.0
        return self.mots_extraits / self.mots_revendiques


# ============================================================================
# 1. DÉTECTION DES SEUILS TYPOGRAPHIQUES
# ============================================================================

class EuropressePagePattern:
    """
    Constantes typographiques du format Europresse Cision (validées mai 2026).

    Ces valeurs ont été dérivées par inspection empirique d'un PDF AFP.
    À vérifier sur d'autres médias (Le Monde, Le Figaro) en cas d'évolution
    du format Europresse.

    Si les seuils changent, modifier ici sans toucher au reste du module.
    """

    # Tailles de police observées
    TAILLE_TITRE_MIN = 16.0            # Stricte : exclut le numéro de page (15pt)
    TAILLE_TITRE_MAX = 30.0
    TAILLE_DROPCAP_MIN = 30.0          # La grosse capitale du 1er paragraphe
    TAILLE_CORPS = 9.8
    TAILLE_METADATA = 8.2

    # Positions Y (haut de page = top petit)
    Y_TITRE_ATTENDU = 186.0            # Le titre commence vers y=186
    Y_TITRE_ZONE_MAX = 280.0           # Le titre ne descend jamais au-delà de y=280

    # Tolérance détection titre
    NB_CHARS_TITRE_MIN = 20            # Un vrai titre fait au moins 20 caractères

    # Pattern ID Europresse
    REGEX_ID = re.compile(
        r'news·(\d{8})·([A-Z0-9]+)·([\w×\-]+)',
        re.UNICODE
    )

    # Mots typiques de la page de couverture / sommaire (à ignorer)
    MOTS_COUVERTURE = {"Documents sauvegardés", "Sommaire"}

    # v2 : marqueurs déterministes de fin d'article (pied de page de copyright
    # Europresse). Le corps est tronqué à la PREMIÈRE occurrence trouvée.
    #   « © 2023 Le Monde. Tous droits réservés. »
    #   « Le présent document est protégé par les lois et conventions
    #     internationales sur le droit d'auteur… »
    #   « Certificat émis le … à des fins de visualisation personnelle… »
    REGEX_FIN_ARTICLE = re.compile(
        r"(?:^|\n)\s*©\s*(?:19|20)\d{2}\b"
        r"|Le présent document est protégé par les lois et conventions"
        r"|Certificat émis le",
        re.IGNORECASE,
    )


# ============================================================================
# 1 bis. NORMALISATION DU NOM DE MÉDIA (v2)
# ============================================================================

# Noms canoniques du corpus du mémoire. Clé = motif recherché (minuscules,
# sans accents ni apostrophes typographiques), valeur = nom normalisé.
MEDIAS_CANONIQUES = {
    "le monde": "Le Monde",
    "les echos": "Les Échos",
    "le figaro": "Le Figaro",
    "liberation": "Libération",
    "l'obs": "L'Obs",
    "le nouvel observateur": "L'Obs",
    "le point": "Le Point",
    "afp": "AFP",
    "agence france-presse": "AFP",
    "agence france presse": "AFP",
}

# Repli : code source présent dans l'identifiant Europresse
# (news·AAAAMMJJ·CODE·…). Seul « AFPD » a été observé de façon certaine dans
# les exports du mémoire ; complétez ce dictionnaire avec les codes de vos
# propres exports avant usage.
CODES_SOURCE_EUROPRESSE = {
    "AFPD": "AFP",
}


def _sans_accents(texte: str) -> str:
    import unicodedata
    texte = texte.replace("’", "'")
    return "".join(c for c in unicodedata.normalize("NFD", texte)
                   if unicodedata.category(c) != "Mn")


def normaliser_media(nom_brut: str, article_id: str = "") -> str:
    """
    Ramène le nom de média lu dans l'encart à un nom canonique.

    1. Recherche d'un titre connu dans la valeur brute
       (« AFP - Infos Economiques » → « AFP », « Le Monde Page » → « Le Monde »).
    2. À défaut (la métadonnée a capté un intitulé de rubrique), repli sur le
       code source de l'identifiant Europresse.
    3. À défaut, la valeur brute est conservée telle quelle.
    """
    brut = _sans_accents((nom_brut or "").lower()).strip()
    for motif, canonique in MEDIAS_CANONIQUES.items():
        if re.search(rf"(?<![\w']){re.escape(motif)}(?!\w)", brut):
            return canonique
    m = EuropressePagePattern.REGEX_ID.search(article_id or "")
    if m and m.group(2) in CODES_SOURCE_EUROPRESSE:
        return CODES_SOURCE_EUROPRESSE[m.group(2)]
    return nom_brut


# ============================================================================
# 2. SEGMENTATION DU PDF EN ARTICLES
# ============================================================================

class EuropresseArticleSegmenter:
    """
    Détermine pour chaque page : est-ce le début d'un nouvel article,
    une continuation, ou une page non-article (couverture/sommaire) ?

    Règle :
      - Page contenant un titre H1 (chars taille TITRE_MIN-MAX en quantité
        ≥ NB_CHARS_TITRE_MIN à proximité de Y_TITRE_ATTENDU) ET un ID news·
        → début d'article
      - Page sans titre H1 mais avec contenu après une page d'article
        → continuation
      - Sinon → ignorée
    """

    def __init__(self, pattern: EuropressePagePattern = None):
        self.pattern = pattern or EuropressePagePattern()

    @staticmethod
    def chars_titre(page, pattern: EuropressePagePattern) -> List[Any]:
        """
        Récupère les caractères qui composent le titre H1 :
        - taille dans la plage [TAILLE_TITRE_MIN, TAILLE_TITRE_MAX]
        - position Y dans la zone haute (top < Y_TITRE_ZONE_MAX)
        """
        return [
            c for c in page.chars
            if pattern.TAILLE_TITRE_MIN < c['size'] < pattern.TAILLE_TITRE_MAX
            and c['top'] < pattern.Y_TITRE_ZONE_MAX
        ]

    def segmenter(self, pdf: "pdfplumber.PDF") -> List[List[int]]:
        """
        Returns:
            Liste de groupes de pages (1-indexed) constituant chacun un article.
            Ex : [[3], [4], [5], [6, 7], [8, 9], [10]]
        """
        groupes: List[List[int]] = []
        groupe_courant: Optional[List[int]] = None

        for page_idx, page in enumerate(pdf.pages):
            page_num = page_idx + 1  # 1-indexed pour cohérence avec le PDF
            est_debut = self._est_debut_article(page)

            if est_debut:
                # Clôt le groupe précédent et en ouvre un nouveau
                if groupe_courant is not None:
                    groupes.append(groupe_courant)
                groupe_courant = [page_num]
            else:
                # Continuation : à condition qu'on ait déjà un groupe ouvert
                # ET que la page ait du contenu textuel (pas couverture vide)
                if groupe_courant is not None and self._a_du_contenu(page):
                    groupe_courant.append(page_num)
                # Sinon (page de couverture / sommaire avant le 1er article)
                # on ignore

        if groupe_courant is not None:
            groupes.append(groupe_courant)

        logger.info(
            f"Segmentation : {len(groupes)} article(s) détecté(s) "
            f"sur {len(pdf.pages)} page(s)."
        )
        return groupes

    def _est_debut_article(self, page) -> bool:
        """Une page commence un article si elle contient un titre H1 + ID news·."""
        # Critère 1 : titre H1 présent (dans la zone haute)
        titre_chars = self.chars_titre(page, self.pattern)
        a_titre = len(titre_chars) >= self.pattern.NB_CHARS_TITRE_MIN

        # Critère 2 : ID news présent
        texte = page.extract_text() or ""
        a_id = bool(self.pattern.REGEX_ID.search(texte))

        return a_titre and a_id

    def _a_du_contenu(self, page) -> bool:
        """Page non-vide (au moins 50 caractères de corps)."""
        texte = page.extract_text() or ""
        return len(texte.strip()) > 50


# ============================================================================
# 3. EXTRACTION DES MÉTADONNÉES
# ============================================================================

class EuropresseMetadataExtractor:
    """
    Extrait les métadonnées de l'encart en tête de la première page d'article.

    L'encart Europresse contient (dans l'ordre, en taille 8.2pt) :
        Nom de la source     : AFP - Infos Economiques
        Type de source       : Presse • Fils de presse
        Couverture géographique : Internationale
        Provenance           : France
        + Date (à droite)    : Vendredi 28 juillet 2023
        + Mots               : 311 mots
        + ID                 : news·20230728·AFPD·tx-par-blw82

    Stratégie : extraire le texte de la zone au-dessus du titre, puis
    appliquer des regex pour récupérer chaque champ.
    """

    MOIS_FR = {
        "janvier": "01", "février": "02", "mars": "03", "avril": "04",
        "mai": "05", "juin": "06", "juillet": "07", "août": "08",
        "septembre": "09", "octobre": "10", "novembre": "11", "décembre": "12",
    }

    def __init__(self, pattern: EuropressePagePattern = None):
        self.pattern = pattern or EuropressePagePattern()

    def extraire(self, page_principale) -> Dict[str, Any]:
        """
        Args:
            page_principale: première page de l'article (objet pdfplumber.Page)

        Returns:
            dict avec les métadonnées extraites + warnings éventuels.
        """
        # Crop : zone au-dessus du titre (y < Y_TITRE - marge)
        # Plus exactement : depuis le haut jusqu'au début du titre
        y_titre_bas = self._trouver_y_bas_titre(page_principale)

        # Si pas de titre détecté, fallback : crop sur 1/4 supérieur
        if y_titre_bas is None:
            y_titre_bas = page_principale.height * 0.3

        zone_meta = page_principale.crop((
            0, 0, page_principale.width, y_titre_bas
        ))
        texte_meta = zone_meta.extract_text() or ""

        warnings = []

        # --- ID Europresse ---
        id_match = self.pattern.REGEX_ID.search(texte_meta)
        if id_match:
            article_id = id_match.group(0)
            date_iso_from_id = self._date_iso_depuis_id(id_match.group(1))
        else:
            article_id = "INCONNU_" + str(id(page_principale))[:8]
            date_iso_from_id = ""
            warnings.append("ID Europresse non trouvé dans l'encart")

        # --- Nom de la source ---
        source = self._extraire_apres_label(texte_meta, "Nom de la source")
        if not source:
            warnings.append("'Nom de la source' non trouvé")

        # --- Type de source ---
        type_src = self._extraire_apres_label(texte_meta, "Type de source")

        # --- Couverture géographique ---
        couv = self._extraire_apres_label(texte_meta, "Couverture géographique")

        # --- Provenance ---
        prov = self._extraire_apres_label(texte_meta, "Provenance")

        # --- Date (format français) ---
        # Stratégie : on cherche d'abord dans l'encart, MAIS on filtre les
        # dates "footer" (date d'export Europresse). L'ID news·YYYYMMDD est
        # la source la plus fiable et prioritaire.
        date_raw, date_iso_from_text = self._extraire_date(texte_meta)

        # Priorité : ID > texte (l'ID est gravé dans le PDF, le texte peut
        # contenir la date d'export du PDF en plus de la date de publication)
        if date_iso_from_id:
            date_iso = date_iso_from_id
            # Si le date_raw du texte ne correspond pas à l'ID, c'est un footer
            if date_raw and not self._date_raw_compatible_avec_id(
                date_raw, date_iso_from_id
            ):
                date_raw = ""  # on jette la date du footer
        else:
            date_iso = date_iso_from_text

        # --- Mots revendiqués ---
        m_mots = re.search(r'(\d+)\s*mots', texte_meta)
        nb_mots = int(m_mots.group(1)) if m_mots else 0

        return {
            "article_id": article_id,
            "source_media": source or "Inconnue",
            "type_source": type_src or "",
            "couverture_geographique": couv or "",
            "provenance": prov or "",
            "date_publication": date_iso,
            "date_publication_raw": date_raw,
            "mots_revendiques": nb_mots,
            "warnings": warnings,
        }

    def _trouver_y_bas_titre(self, page) -> Optional[float]:
        """Retourne la position Y du bas du titre H1 (pour cropper en-dessous)."""
        titre_chars = EuropresseArticleSegmenter.chars_titre(page, self.pattern)
        if not titre_chars:
            return None
        return max(c['bottom'] for c in titre_chars)

    def _extraire_apres_label(self, texte: str, label: str) -> str:
        """
        Récupère la valeur sur la/les ligne(s) suivant un label.

        Robustesse : les vignettes d'aperçu Europresse insèrent parfois des
        lignes parasites ("Page", "Page 6", numéros) juste après le label.
        On saute ces parasites pour trouver la vraie valeur.
        """
        lignes = texte.split('\n')
        autres_labels = {
            "Nom de la source", "Type de source",
            "Couverture géographique", "Provenance", "Périodicité",
        }
        for i, ligne in enumerate(lignes):
            if ligne.strip() == label or ligne.strip().startswith(label):
                # Examiner jusqu'à 4 lignes suivantes pour trouver une valeur valable
                for j in range(i + 1, min(i + 5, len(lignes))):
                    valeur = lignes[j].strip()
                    if not valeur:
                        continue
                    if valeur in autres_labels:
                        break  # on a atteint le label suivant sans rien trouver
                    valeur = self._nettoyer_valeur_meta(valeur)
                    # Rejeter les parasites de vignette (mot "Page" seul, nombre seul, vide)
                    if not valeur or valeur.lower() == "page" or valeur.isdigit():
                        continue
                    return valeur
        return ""

    def _nettoyer_valeur_meta(self, valeur: str) -> str:
        """
        Nettoie une valeur de métadonnée des parasites issus de la vignette
        d'aperçu (numéros de page, mot 'Page', dates qui débordent).

        Ex : "Le Monde Page" → "Le Monde"
             "Le Monde 9"    → "Le Monde"
        """
        # Retirer "Page" et les numéros de page en fin de chaîne
        valeur = re.sub(r'\s+Page\s*\d*\s*$', '', valeur, flags=re.IGNORECASE)
        valeur = re.sub(r'\s+\d+\s*$', '', valeur)
        # Retirer une date française qui aurait débordé
        valeur = re.sub(
            r'\s+(?:lundi|mardi|mercredi|jeudi|vendredi|samedi|dimanche).*$',
            '', valeur, flags=re.IGNORECASE
        )
        return valeur.strip()

    def _extraire_date(self, texte: str) -> Tuple[str, str]:
        """
        Extrait la date au format "Vendredi 28 juillet 2023".
        Retourne (date_brute, date_iso).
        """
        pattern_date = re.compile(
            r'(?:lundi|mardi|mercredi|jeudi|vendredi|samedi|dimanche)\s+'
            r'(\d{1,2})\s+(' + '|'.join(self.MOIS_FR.keys()) + r')\s+(\d{4})',
            re.IGNORECASE
        )
        m = pattern_date.search(texte)
        if not m:
            return "", ""

        date_raw = m.group(0)
        jour = m.group(1).zfill(2)
        mois = self.MOIS_FR[m.group(2).lower()]
        annee = m.group(3)
        return date_raw, f"{annee}-{mois}-{jour}"

    def _date_raw_compatible_avec_id(self, date_raw: str, date_iso: str) -> bool:
        """Vérifie que la date trouvée dans le texte correspond à l'année/mois de l'ID."""
        if not date_iso:
            return True
        annee, mois, _ = date_iso.split("-")
        if annee not in date_raw:
            return False
        # Vérifier le mois en lettres
        mois_inverse = {v: k for k, v in self.MOIS_FR.items()}
        mois_nom = mois_inverse.get(mois, "")
        if mois_nom and mois_nom not in date_raw.lower():
            return False
        return True

    def _date_iso_depuis_id(self, yyyymmdd: str) -> str:
        """Convertit '20230728' en '2023-07-28'."""
        if len(yyyymmdd) == 8:
            return f"{yyyymmdd[:4]}-{yyyymmdd[4:6]}-{yyyymmdd[6:8]}"
        return ""


# ============================================================================
# 4. EXTRACTION DU CORPS DE L'ARTICLE
# ============================================================================

class EuropresseBodyExtractor:
    """
    Extrait le corps de l'article (titre + texte) en gérant la mise en
    deux colonnes typique d'Europresse.

    Stratégie :
      1. Trouver la position Y du bas du titre H1 → début du corps
      2. Détecter la frontière X entre les deux colonnes (analyse des gaps)
      3. Extraire colonne gauche puis colonne droite
      4. Concaténer dans l'ordre de lecture
      5. Nettoyer (recollage césures, gestion des "mots collés")
    """

    def __init__(self, pattern: EuropressePagePattern = None):
        self.pattern = pattern or EuropressePagePattern()

    def extraire(
        self, pages: List[Any], page_principale_idx: int = 0
    ) -> Tuple[str, str]:
        """
        Args:
            pages: liste d'objets pdfplumber.Page constituant l'article
            page_principale_idx: index dans `pages` de la page contenant le titre

        Returns:
            (titre, texte_corps)
        """
        page_principale = pages[page_principale_idx]
        titre = self._extraire_titre(page_principale)

        morceaux_corps = []
        for i, page in enumerate(pages):
            y_debut = self._y_debut_corps(page, est_principale=(i == 0))
            texte = self._extraire_corps_multicolonnes(page, y_debut)
            morceaux_corps.append(texte)

        texte_complet = "\n\n".join(morceaux_corps)
        texte_complet = self.tronquer_fin_article(texte_complet)
        texte_complet = self._nettoyer(texte_complet)

        return titre, texte_complet

    def tronquer_fin_article(self, texte: str) -> str:
        """
        v2 : coupe le texte à la première mention de copyright Europresse.

        Corrige la sur-extraction observée sur les cahiers spéciaux, où le
        corps d'un article absorbait les articles suivants faute de frontière
        détectée (§2.2.2 du mémoire : 13 articles rectifiés).
        """
        m = self.pattern.REGEX_FIN_ARTICLE.search(texte)
        if m:
            return texte[:m.start()]
        return texte

    def _extraire_corps_multicolonnes(self, page, y_debut: float) -> str:
        """
        Extrait le corps en gérant un nombre arbitraire de colonnes (1, 2, 3...).

        Méthode (robuste car indépendante du nombre de colonnes) :
          1. Récupérer les mots de la zone du corps
          2. Détecter les bornes gauches des colonnes par clustering des x0
          3. Assigner chaque mot à sa colonne
          4. Lire colonne par colonne (gauche→droite), ligne par ligne (haut→bas)
        """
        y_fin = page.height - 70  # exclure le footer
        words = page.extract_words(x_tolerance=1, y_tolerance=2)
        words_corps = [w for w in words if y_debut < w['top'] < y_fin]

        if not words_corps:
            return ""

        # 1. Détecter les bornes de colonnes
        bornes = self._detecter_bornes_colonnes(words_corps, page.width)

        # 2. Assigner chaque mot à une colonne (selon la borne la plus proche à gauche)
        colonnes: Dict[int, List[Any]] = {i: [] for i in range(len(bornes))}
        for w in words_corps:
            # Trouver l'index de colonne : dernière borne <= x0 du mot
            idx_col = 0
            for i, b in enumerate(bornes):
                if w['x0'] >= b - 5:  # tolérance 5pt
                    idx_col = i
            colonnes[idx_col].append(w)

        # 3. Pour chaque colonne, trier par Y puis reconstituer les lignes
        morceaux = []
        for idx_col in sorted(colonnes.keys()):
            mots_col = colonnes[idx_col]
            if not mots_col:
                continue
            texte_col = self._reconstituer_colonne(mots_col)
            if texte_col.strip():
                morceaux.append(texte_col)

        return "\n".join(morceaux)

    def _detecter_bornes_colonnes(
        self, words_corps: List[Any], page_width: float
    ) -> List[float]:
        """
        Détecte les bornes gauches des colonnes par clustering des positions x0.

        Principe : les débuts de lignes de chaque colonne créent des pics
        marqués dans la distribution des x0 (beaucoup de lignes commencent
        exactement au même x). On identifie ces pics.

        Returns:
            Liste triée des x de début de colonne (ex: [54, 228, 402]).
        """
        # Histogramme des x0 (buckets de 3pt pour absorber le bruit)
        bucket_size = 3
        buckets = Counter(round(w['x0'] / bucket_size) * bucket_size for w in words_corps)

        # Un "début de colonne" est un bucket avec beaucoup de mots (≥ 40% du max)
        if not buckets:
            return [0.0]
        max_count = max(buckets.values())
        seuil = max(max_count * 0.4, 5)  # au moins 5 lignes

        pics = sorted([x for x, n in buckets.items() if n >= seuil])

        if not pics:
            return [min(w['x0'] for w in words_corps)]

        # Fusionner les pics trop proches (< 40pt = même colonne)
        # car une colonne peut avoir 2 x0 fréquents proches (justification)
        bornes = [pics[0]]
        for x in pics[1:]:
            if x - bornes[-1] >= 40:  # nouvelle colonne si gap ≥ 40pt
                bornes.append(x)

        return bornes

    def _reconstituer_colonne(self, mots: List[Any]) -> str:
        """
        Reconstitue le texte d'une colonne : trie les mots par ligne (Y),
        puis par X dans chaque ligne, et joint avec des espaces.
        """
        # Grouper les mots par ligne (tolérance Y de 4pt)
        mots_tries = sorted(mots, key=lambda w: (w['top'], w['x0']))
        lignes: List[List[Any]] = []
        ligne_courante: List[Any] = []
        y_ref = None

        for w in mots_tries:
            if y_ref is None or abs(w['top'] - y_ref) <= 4:
                ligne_courante.append(w)
                y_ref = w['top'] if y_ref is None else y_ref
            else:
                lignes.append(ligne_courante)
                ligne_courante = [w]
                y_ref = w['top']
        if ligne_courante:
            lignes.append(ligne_courante)

        # Reconstituer chaque ligne
        textes_lignes = []
        for ligne in lignes:
            ligne_triee = sorted(ligne, key=lambda w: w['x0'])
            textes_lignes.append(' '.join(w['text'] for w in ligne_triee))

        return '\n'.join(textes_lignes)

    def _extraire_titre(self, page) -> str:
        """Extrait le titre H1 (taille 18.8pt typiquement, dans la zone haute)."""
        titre_chars = EuropresseArticleSegmenter.chars_titre(page, self.pattern)
        if not titre_chars:
            return ""

        # Tri par ligne (Y) puis par X
        titre_chars.sort(key=lambda c: (round(c['top'] / 5) * 5, c['x0']))

        # Reconstituer en insérant des espaces là où il y a un gap horizontal
        morceaux = []
        prev_char = None
        for c in titre_chars:
            if prev_char is not None:
                gap_y = abs(c['top'] - prev_char['top'])
                gap_x = c['x0'] - prev_char['x1']
                if gap_y > 5:  # nouvelle ligne
                    morceaux.append(' ')
                elif gap_x > 2:  # espace inter-mot
                    morceaux.append(' ')
            morceaux.append(c['text'])
            prev_char = c

        # Filtrer le numéro de page en fin de titre (drop cap inverse)
        titre_brut = ''.join(morceaux).strip()
        # Enlever un éventuel chiffre isolé en fin (numéro de page intégré)
        titre_brut = re.sub(r'\s+\d{1,2}\s*$', '', titre_brut)
        return titre_brut

    def _y_debut_corps(self, page, est_principale: bool) -> float:
        """Position Y à partir de laquelle commence le corps de l'article."""
        if est_principale:
            titre_chars = EuropresseArticleSegmenter.chars_titre(page, self.pattern)
            if titre_chars:
                return max(c['bottom'] for c in titre_chars) + 5
            return 250  # fallback
        else:
            # Page de continuation : commence après l'en-tête "Documents sauvegardés..."
            # qui occupe les ~80 premiers points
            return 80

    def _nettoyer(self, texte: str) -> str:
        """
        Nettoie le texte extrait :
          - Recolle les césures (ex: "consomma-\\ntion" → "consommation")
          - Recolle les drop caps Europresse (ex: "P\\naris" → "Paris")
          - Insère des espaces dans les mots collés
          - Normalise les espaces multiples et les sauts de ligne
        """
        # Recollage césures (mot-tiret\nmot → motmot)
        texte = re.sub(r'(\w)-\s*\n\s*(\w)', r'\1\2', texte)

        # Recollage drop caps : une majuscule seule sur une ligne suivie d'une
        # minuscule en début de ligne suivante → on les fusionne
        # Ex: "P\naris, 28 juil" → "Paris, 28 juil"
        texte = re.sub(
            r'\n([A-Z])\n([a-zà-ÿ])',
            r'\n\1\2',
            texte
        )
        # Cas où le drop cap est en début de texte
        texte = re.sub(
            r'^([A-Z])\n([a-zà-ÿ])',
            r'\1\2',
            texte
        )

        # Nettoyage lignes
        lignes = texte.split('\n')
        nouvelles = []
        for ligne in lignes:
            ligne = ligne.strip()
            if ligne:
                nouvelles.append(ligne)
            elif nouvelles and nouvelles[-1] != "":
                nouvelles.append("")  # paragraphe break

        texte = '\n'.join(nouvelles)

        # Réduit les sauts multiples
        texte = re.sub(r'\n{3,}', '\n\n', texte)

        # Espaces multiples
        texte = re.sub(r' {2,}', ' ', texte)

        return texte.strip()


# ============================================================================
# 5. ORCHESTRATEUR PRINCIPAL
# ============================================================================

class EuropresseParser:
    """
    Parser principal. Convertit un PDF Europresse en liste d'ArticleEuropresse.

    Usage :
        parser = EuropresseParser()
        articles = parser.parser("mon_export.pdf")
        for art in articles:
            print(art.article_id, art.source_media, art.titre)
    """

    def __init__(self):
        self.pattern = EuropressePagePattern()
        self.segmenter = EuropresseArticleSegmenter(self.pattern)
        self.meta_extractor = EuropresseMetadataExtractor(self.pattern)
        self.body_extractor = EuropresseBodyExtractor(self.pattern)
        logger.info("EuropresseParser initialisé.")

    def parser(self, chemin_pdf: str) -> List[ArticleEuropresse]:
        """
        Parse un PDF Europresse.

        Args:
            chemin_pdf: chemin vers le fichier PDF

        Returns:
            Liste d'ArticleEuropresse.
        """
        chemin = Path(chemin_pdf)
        if not chemin.exists():
            raise FileNotFoundError(f"PDF introuvable : {chemin}")

        articles: List[ArticleEuropresse] = []

        with pdfplumber.open(str(chemin)) as pdf:
            groupes_pages = self.segmenter.segmenter(pdf)

            for groupe in groupes_pages:
                # Conversion 1-indexed → 0-indexed pour accès pdfplumber
                pages_obj = [pdf.pages[i - 1] for i in groupe]
                try:
                    article = self._parser_groupe(
                        pages_obj, groupe, chemin.name
                    )
                    if article:
                        articles.append(article)
                except Exception as e:
                    logger.error(
                        f"Erreur parsing groupe {groupe} : {e}", exc_info=True
                    )

        logger.info(
            f"Parser : {len(articles)} article(s) extrait(s) de {chemin.name}."
        )
        return articles

    def _parser_groupe(
        self, pages: List[Any], numeros_pages: List[int], nom_pdf: str
    ) -> Optional[ArticleEuropresse]:
        """Parse un groupe de pages constituant un article."""

        # 1. Métadonnées
        meta = self.meta_extractor.extraire(pages[0])

        # 2. Titre + corps
        titre, texte = self.body_extractor.extraire(pages, page_principale_idx=0)

        # 3. Comptage de mots
        mots_extraits = len(texte.split())

        # 4. Construction
        article = ArticleEuropresse(
            article_id=meta["article_id"],
            source_pdf=nom_pdf,
            pages_dans_pdf=numeros_pages,
            source_media=normaliser_media(meta["source_media"],
                                          meta["article_id"]),
            source_media_brut=meta["source_media"],
            type_source=meta["type_source"],
            couverture_geographique=meta["couverture_geographique"],
            provenance=meta["provenance"],
            date_publication=meta["date_publication"],
            date_publication_raw=meta["date_publication_raw"],
            titre=titre,
            texte=texte,
            mots_revendiques=meta["mots_revendiques"],
            mots_extraits=mots_extraits,
            warnings=meta["warnings"],
        )

        # Diagnostics post-extraction
        if article.mots_revendiques > 0:
            taux = article.taux_extraction
            if taux < 0.7:
                article.warnings.append(
                    f"Extraction faible : {mots_extraits}/{article.mots_revendiques} "
                    f"mots ({taux:.0%})"
                )
            elif taux > 1.3:
                article.warnings.append(
                    f"Extraction excessive : {mots_extraits}/{article.mots_revendiques} "
                    f"mots ({taux:.0%}) — éléments parasites probables"
                )

        if not article.titre:
            article.warnings.append("Titre vide")
        if not article.date_publication:
            article.warnings.append("Date de publication non extraite")

        return article


# ============================================================================
# 6. MODE DIAGNOSTIC
# ============================================================================

def diagnostiquer(chemin_pdf: str) -> None:
    """
    Affiche un rapport de diagnostic sur un PDF Europresse :
    pages détectées, articles segmentés, qualité d'extraction.

    À utiliser pour vérifier la robustesse du parser sur un nouveau PDF
    AVANT d'intégrer ce PDF au corpus.
    """
    print("=" * 70)
    print(f"DIAGNOSTIC EUROPRESSE — {chemin_pdf}")
    print("=" * 70)

    parser = EuropresseParser()
    articles = parser.parser(chemin_pdf)

    if not articles:
        print("⚠️  Aucun article extrait. Le PDF a-t-il le format Europresse attendu ?")
        return

    print(f"\n{len(articles)} article(s) extrait(s).\n")
    print(f"{'#':>3}  {'ID':<35}  {'Source':<25}  {'Date':<12}  {'Mots':>10}  {'OK?':<5}")
    print("-" * 110)

    ok_count = 0
    for i, art in enumerate(articles, 1):
        taux = art.taux_extraction * 100 if art.mots_revendiques else 0
        ok = "✅" if 70 <= taux <= 130 and not art.warnings else "⚠️"
        if ok == "✅":
            ok_count += 1
        print(
            f"{i:>3}  {art.article_id[:35]:<35}  "
            f"{art.source_media[:25]:<25}  "
            f"{art.date_publication:<12}  "
            f"{art.mots_extraits:>4}/{art.mots_revendiques:<5}  {ok}"
        )

        for w in art.warnings:
            print(f"       ⚠ {w}")

    print(f"\nQualité globale : {ok_count}/{len(articles)} articles propres.")

    # Statistiques sur les médias
    from collections import Counter
    medias = Counter(a.source_media for a in articles)
    print(f"\nMédias présents ({len(medias)}) :")
    for media, n in medias.most_common():
        print(f"  - {media}: {n} article(s)")

    # Statistiques temporelles
    dates = [a.date_publication for a in articles if a.date_publication]
    if dates:
        print(f"\nPériode couverte : {min(dates)} → {max(dates)}")


# ============================================================================
# 7. EXPORT VERS LE PIPELINE AVAL
# ============================================================================

def vers_csv_pipeline(
    articles: List[ArticleEuropresse], chemin_csv: str
) -> None:
    """
    Exporte les articles au format CSV attendu par le pipeline (M1 → M5).

    Format compatible avec `charger_corpus(chemin_csv)` du TUTO :
        id;media;date;titre;texte;sujet
    """
    import csv

    with open(chemin_csv, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f, delimiter=";", quoting=csv.QUOTE_ALL)
        writer.writerow(["id", "media", "date", "titre", "texte", "sujet"])
        for art in articles:
            writer.writerow([
                art.article_id,
                art.source_media,
                art.date_publication,
                art.titre,
                art.texte,
                art.sujet,  # à compléter manuellement après extraction
            ])
    logger.info(f"CSV exporté : {chemin_csv} ({len(articles)} articles)")


# ============================================================================
# 8. POINT D'ENTRÉE
# ============================================================================

if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage : python module0_parser_europresse.py <chemin_pdf> [csv_sortie]")
        sys.exit(1)

    chemin_pdf = sys.argv[1]
    diagnostiquer(chemin_pdf)

    if len(sys.argv) >= 3:
        parser = EuropresseParser()
        articles = parser.parser(chemin_pdf)
        vers_csv_pipeline(articles, sys.argv[2])
        print(f"\n→ Exporté vers {sys.argv[2]}")
