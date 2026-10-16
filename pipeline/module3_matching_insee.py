"""
MODULE 3 : Client API INSEE BDM (Banque de Données Macroéconomiques)
=====================================================================

Mémoire INSEEC MSc — Data & Marketing Digital — 2025-2026
Problématique : "Dans quelle mesure peut-on détecter de la désinformation
                 médiatique par la donnée ?"

Ce module récupère les valeurs officielles INSEE pour confronter les claims
chiffrés (régime 1) extraits de la presse.

ENDPOINT (vérifié mai 2026)
    https://www.bdm.insee.fr/series/sdmx/data/SERIES_BDM/{idbank}?{params}
    - REST, norme SDMX 2.1, réponse XML
    - GRATUIT, SANS authentification (pas de token)
    - Jusqu'à 400 idbank par requête (séparés par "+")
    - Paramètres : startPeriod, endPeriod, lastNObservations, includeHistory

    NOTE : le nouveau portail portail-api.insee.fr (2025) propose aussi
    Melodi (JSON), mais l'endpoint bdm.insee.fr/series/sdmx reste actif et
    ne nécessite pas de compte. On l'utilise pour la simplicité.

LES TROIS DÉFIS TRAITÉS (cf. audit)
    1. MATCHING indicateur→idbank : table de correspondance documentée,
       avec gestion des sous-séries (chômage BIT vs catégorie A, etc.)
    2. RÉVISIONS temporelles : paramètre includeHistory=true pour récupérer
       la valeur telle que publiée à une date donnée (pas la valeur révisée)
    3. SOURCES multiples : détection de la source citée dans le texte pour
       choisir la bonne base (INSEE vs Eurostat vs France Travail)

⚠️ EXÉCUTION
    Ce client doit être exécuté sur une machine avec accès Internet
    (l'environnement de développement IA n'a pas accès à bdm.insee.fr).
    Le mode --mock permet de tester la logique sans réseau.

Entrée  : ClaimStructure (Module 2) en régime 1
Sortie  : DonneeOfficielle (valeur INSEE + métadonnées)

Auteur : Florian, mai 2026.
"""

from __future__ import annotations
import re
import json
import time
import logging
import sqlite3
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import List, Optional, Dict, Tuple
from datetime import datetime

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s")
logger = logging.getLogger("Module3")

# Import réseau optionnel (le mock fonctionne sans)
try:
    import urllib.request
    import urllib.error
    import xml.etree.ElementTree as ET
    _RESEAU_DISPO = True
except ImportError:
    _RESEAU_DISPO = False


# ============================================================================
# STRUCTURES
# ============================================================================

@dataclass
class DonneeOfficielle:
    """Valeur officielle récupérée pour vérifier un claim."""
    idbank: str
    libelle: str                 # nom de la série INSEE
    valeur: Optional[float]
    periode: str                 # période de l'observation (2023-07, 2023-Q4)
    unite: str
    source: str = "INSEE-BDM"
    date_recuperation: str = ""
    revisions: List[Dict] = field(default_factory=list)  # historique si demandé
    trouve: bool = False
    note: str = ""

    def to_dict(self):
        return asdict(self)


# ============================================================================
# TABLE DE CORRESPONDANCE INDICATEUR → IDBANK
# ============================================================================

class CorrespondanceIdbank:
    """
    Table de correspondance entre les indicateurs détectés (Module 2) et
    les identifiants de séries INSEE (idbank).

    ⚠️ POINT MÉTHODOLOGIQUE CRITIQUE
    Un même mot journalistique ("chômage") peut correspondre à plusieurs
    séries. Le choix de la série de référence est un CHOIX MÉTHODOLOGIQUE
    qui doit être justifié dans le mémoire et validé manuellement.

    Les idbank ci-dessous sont les séries de référence les plus couramment
    citées par la presse. À VÉRIFIER sur insee.fr/fr/statistiques/series
    avant le run de production — les idbank peuvent évoluer.

    Pour trouver/vérifier un idbank :
      1. Aller sur https://www.insee.fr/fr/statistiques/serie/{idbank}
      2. Ou parcourir https://www.bdm.insee.fr/series/sdmx/dataflow
    """

    # ════════════════════════════════════════════════════════════════════
    # idbank VÉRIFIÉS via le fichier officiel correspondance_idbank_dimension
    # (INSEE, version 202603). Dimensions contrôlées une à une.
    # ════════════════════════════════════════════════════════════════════
    # DÉCISIONS MÉTHODOLOGIQUES À TRANCHER PAR L'AUTEUR :
    #   - inflation & chômage : choix FM (métropole) vs FE/France hors Mayotte.
    #     Choisir selon le champ géographique cité majoritairement par les
    #     articles du corpus. Par défaut : France entière / hors Mayotte
    #     (champ de communication officiel INSEE depuis 2021).
    #   - déficit en % du PIB : N'EXISTE PAS comme série BDM (l'INSEE ne sert
    #     que les euros courants). → traité hors fact-checking automatique
    #     (à basculer en régime 2). Voir note ci-dessous.
    TABLE = {
        "inflation": {
            # IPC, ensemble des ménages, glissement annuel, %, base 2025, vivante
            "principal": "011814632",   # FE = France (entière)
            "libelle": "IPC - Ensemble des ménages - France - Glissement annuel (%)",
            "frequence": "M",
            "alternatives": {
                "metropole": "011814614",  # FM = France métropolitaine
            },
            "unite": "%",
        },
        "chômage": {
            # Taux de chômage BIT, ensemble, 15 ans et +, CVS, vivante
            "principal": "001688527",   # FR-D976 = France hors Mayotte
            "libelle": "Taux de chômage au sens du BIT - France hors Mayotte - "
                       "Ensemble - 15 ans ou plus - CVS (%)",
            "frequence": "T",
            "alternatives": {
                "metropole": "001688526",  # FM = France métropolitaine
                "categorie_a": None,  # DEFM cat A = France Travail, hors BIT
            },
            "unite": "%",
        },
        "PIB": {
            # Taux de croissance du PIB, volume chaîné, CVS-CJO, vivante
            "principal": "011794844",
            "libelle": "PIB - Taux de croissance trimestriel en volume - CVS-CJO (%)",
            "frequence": "T",
            "alternatives": {},
            "unite": "%",
        },
        "dette": {
            # Dette Maastricht, APU (S13), % du PIB, France, vivante
            "principal": "010777608",
            "libelle": "Dette publique au sens de Maastricht - APU - (% du PIB)",
            "frequence": "T",
            "alternatives": {},
            "unite": "% PIB",
        },
        "déficit": {
            # ⚠️ Le déficit en % du PIB N'A PAS d'idbank dans la BDM.
            # Seul existe le besoin de financement B9NF des APU en euros courants
            # (ex : 001718848, base 2010). Le ratio "X% du PIB" est calculé par
            # l'INSEE mais non servi comme série.
            # RECOMMANDATION : traiter le déficit en % comme un claim RÉGIME 2
            # (non fact-checkable automatiquement contre une série unique).
            "principal": None,
            "libelle": "Déficit public (% du PIB) — non disponible en série BDM",
            "frequence": "A",
            "alternatives": {
                "euros_b9nf_apu": "001718848",  # déficit en € courants (base 2010)
            },
            "unite": "% PIB",
        },
    }

    @classmethod
    def resoudre(cls, indicateur: str, phrase: str = "") -> Optional[Dict]:
        """
        Retourne la fiche idbank pour un indicateur, en désambiguïsant selon
        la phrase si possible.
        """
        if indicateur not in cls.TABLE:
            return None

        fiche = dict(cls.TABLE[indicateur])
        p = phrase.lower()

        # Désambiguïsation pour l'inflation : IPCH si "harmonisé" cité
        if indicateur == "inflation":
            if "harmonisé" in p or "ipch" in p:
                fiche["principal"] = fiche["alternatives"].get("ipch", fiche["principal"])
                fiche["libelle"] = "IPCH - Indice harmonisé - Glissement annuel (%)"

        return fiche

    @classmethod
    def detecter_source_citee(cls, phrase: str) -> str:
        """
        Détecte la source officielle citée dans la phrase, pour éviter de
        comparer un chiffre Pôle emploi/France Travail à une série INSEE BIT.
        """
        p = phrase.lower()
        if "france travail" in p or "pôle emploi" in p or "defm" in p or "catégorie a" in p:
            return "France Travail (DEFM)"  # hors périmètre INSEE BIT
        if "eurostat" in p:
            return "Eurostat"
        if "ocde" in p:
            return "OCDE"
        if "banque de france" in p:
            return "Banque de France"
        if "insee" in p or "institut national" in p:
            return "INSEE"
        return "non précisée"


# ============================================================================
# CLIENT API BDM
# ============================================================================

class ClientBDM:
    """
    Client pour l'API SDMX de la BDM INSEE.

    Modes :
      - production : interroge réellement bdm.insee.fr (nécessite Internet)
      - mock : retourne des valeurs simulées (pour test sans réseau)

    Cache : SQLite local pour éviter de réinterroger les mêmes séries.
    """

    BASE_URL = "https://www.bdm.insee.fr/series/sdmx/data/SERIES_BDM"

    # Valeurs mock (issues de la grille des événements INSEE)
    # Format : (idbank, periode) → valeur. idbank mis à jour (vérifiés CSV).
    # ⚠️ Valeurs de DÉMONSTRATION, saisies à la main d'après les premières
    # publications INSEE : elles ne sont pas garanties et ont pu être révisées
    # depuis. Seul le mode « production » fait foi.
    MOCK_VALEURS = {
        ("011814632", "2023-07"): 4.3,
        ("011814632", "2023-03"): 5.6,
        ("011814632", "2023-08"): 4.8,
        ("011814632", "2023-09"): 4.9,
        ("011814632", "2023-06"): 4.5,
        ("011814632", "2024-08"): 1.9,
        ("001688527", "2023-Q4"): 7.5,
        ("001688527", "2023-Q3"): 7.4,
        ("001688527", "2023-Q2"): 7.2,
        ("001688527", "2023-Q1"): 7.1,
        ("001688527", "2024-Q1"): 7.5,
        ("001688527", "2024-Q2"): 7.3,
        ("011794844", "2023-Q4"): 0.1,
        ("011794844", "2024-Q2"): 0.2,
        ("010777608", "2023-Q2"): 111.8,
    }

    def __init__(self, mode: str = "mock", cache_path: str = "cache_insee.db",
                 delai_requetes: float = 0.5):
        self.mode = mode
        self.delai = delai_requetes
        self.cache_path = cache_path
        self._init_cache()
        logger.info(f"ClientBDM initialisé (mode={mode})")

    def _init_cache(self):
        """Initialise le cache SQLite."""
        self.conn = sqlite3.connect(self.cache_path)
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS cache_series (
                idbank TEXT, periode TEXT, valeur REAL, libelle TEXT,
                date_recup TEXT, raw_xml TEXT,
                PRIMARY KEY (idbank, periode)
            )
        """)
        self.conn.commit()

    def recuperer(self, idbank: str, periode: str,
                  libelle: str = "", inclure_revisions: bool = False
                  ) -> DonneeOfficielle:
        """
        Récupère la valeur d'une série INSEE pour une période donnée.

        Args:
            idbank: identifiant de la série
            periode: période recherchée (2023-07, 2023-Q4, 2023)
            libelle: libellé humain de la série
            inclure_revisions: si True, demande l'historique des révisions

        Returns:
            DonneeOfficielle
        """
        # Correctif (octobre 2026) : en v1, le mode mock lisait ET écrivait le
        # même cache SQLite que le mode production. Une valeur simulée pouvait
        # donc ressortir plus tard, en production, étiquetée « INSEE-BDM
        # (cache) ». Le mock ne touche désormais plus au cache.
        if self.mode == "mock":
            return self._recuperer_mock(idbank, periode, libelle)

        # 1. Vérifier le cache
        cached = self._lire_cache(idbank, periode)
        if cached is not None:
            return cached

        # 2. Interroger l'API
        donnee = self._recuperer_api(idbank, periode, libelle, inclure_revisions)

        # 3. Mettre en cache si trouvé
        if donnee.trouve:
            self._ecrire_cache(donnee)

        return donnee

    def _recuperer_mock(self, idbank: str, periode: str,
                        libelle: str) -> DonneeOfficielle:
        """Mode mock : retourne une valeur simulée."""
        valeur = self.MOCK_VALEURS.get((idbank, periode))
        return DonneeOfficielle(
            idbank=idbank,
            libelle=libelle or "(mock)",
            valeur=valeur,
            periode=periode,
            unite="%",
            source="MOCK",
            date_recuperation=datetime.now().isoformat(),
            trouve=valeur is not None,
            note="Valeur simulée (mode mock)" if valeur is not None
                 else "Non couvert par la mock DB",
        )

    def _recuperer_api(self, idbank: str, periode: str, libelle: str,
                       inclure_revisions: bool) -> DonneeOfficielle:
        """
        Mode production : interroge réellement l'API BDM.

        ⚠️ À exécuter sur une machine avec accès Internet.
        """
        if not _RESEAU_DISPO:
            return DonneeOfficielle(idbank, libelle, None, periode, "",
                                    trouve=False, note="urllib indisponible")

        # Construction de l'URL
        params = []
        # On cible la période : startPeriod = endPeriod pour une seule observation
        # (l'API filtre par période ; le format diffère mensuel/trimestriel)
        params.append(f"startPeriod={periode}")
        params.append(f"endPeriod={periode}")
        if inclure_revisions:
            params.append("includeHistory=true")

        url = f"{self.BASE_URL}/{idbank}?" + "&".join(params)

        try:
            time.sleep(self.delai)  # politesse / rate limiting
            # L'INSEE renvoie du SDMX StructureSpecific 2.1. On ne force pas un
            # format generic (qui pourrait être refusé) ; on accepte le XML SDMX.
            req = urllib.request.Request(
                url, headers={
                    "Accept": "application/vnd.sdmx.structurespecificdata+xml;version=2.1, "
                              "application/xml"
                }
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                xml_brut = resp.read().decode("utf-8")
            return self._parser_sdmx(xml_brut, idbank, periode, libelle,
                                     inclure_revisions)
        except urllib.error.HTTPError as e:
            return DonneeOfficielle(idbank, libelle, None, periode, "",
                                    trouve=False,
                                    note=f"HTTP {e.code} : {e.reason}")
        except Exception as e:
            return DonneeOfficielle(idbank, libelle, None, periode, "",
                                    trouve=False,
                                    note=f"Erreur : {type(e).__name__} {e}")

    def _parser_sdmx(self, xml_brut: str, idbank: str, periode: str,
                     libelle: str, inclure_revisions: bool) -> DonneeOfficielle:
        """
        Parse la réponse SDMX-XML de l'INSEE.

        ⚠️ L'INSEE utilise le format SDMX "StructureSpecific" (et NON "generic").
        Dans ce format, période et valeur sont des ATTRIBUTS de la balise <Obs>,
        pas des sous-éléments. Structure réelle (vérifiée mai 2026) :

            <Series IDBANK="001688527" TITLE_FR="..." UNIT_MEASURE="POURCENT"
                    DECIMALS="1" ...>
              <Obs TIME_PERIOD="2026-Q1" OBS_VALUE="8.1" OBS_STATUS="A"
                   OBS_QUAL="DEF" OBS_TYPE="A"/>
              <Obs TIME_PERIOD="2025-Q4" OBS_VALUE="7.9" .../>
            </Series>

        Attributs utiles :
          - TITLE_FR        : libellé complet de la série
          - UNIT_MEASURE    : unité (POURCENT, EUROS...)
          - DECIMALS        : précision officielle (nb de décimales)
          - OBS_QUAL        : DEF = définitif, autre = provisoire/révisable
        """
        try:
            root = ET.fromstring(xml_brut)
        except ET.ParseError as e:
            return DonneeOfficielle(idbank, libelle, None, periode, "",
                                    trouve=False, note=f"XML invalide : {e}")

        def localname(tag):
            return tag.split("}")[-1] if "}" in tag else tag

        # 1. Trouver l'élément Series (et récupérer ses métadonnées)
        serie_elem = None
        for elem in root.iter():
            if localname(elem.tag) == "Series":
                serie_elem = elem
                break

        if serie_elem is None:
            return DonneeOfficielle(idbank, libelle, None, periode, "",
                                    trouve=False, note="Aucune série dans la réponse")

        # Métadonnées de la série (attributs)
        attrs_serie = serie_elem.attrib
        libelle_serie = attrs_serie.get("TITLE_FR", libelle)
        unite_serie = attrs_serie.get("UNIT_MEASURE", "")
        decimals = attrs_serie.get("DECIMALS", "")

        # 2. Parcourir les observations (attributs de <Obs>)
        valeur = None
        qualite = ""
        revisions = []
        for obs in serie_elem:
            if localname(obs.tag) != "Obs":
                continue
            a = obs.attrib
            per_obs = a.get("TIME_PERIOD")
            val_obs = a.get("OBS_VALUE")
            qual_obs = a.get("OBS_QUAL", "")  # DEF = définitif

            if inclure_revisions and val_obs is not None:
                revisions.append({"periode": per_obs, "valeur": val_obs,
                                  "qualite": qual_obs})

            if per_obs == periode and val_obs is not None:
                try:
                    valeur = float(val_obs)
                    qualite = qual_obs
                except (ValueError, TypeError):
                    pass

        note = ""
        if valeur is None:
            note = f"Période {periode} non trouvée dans la série"
        elif qualite and qualite != "DEF":
            note = f"⚠️ Valeur non définitive (OBS_QUAL={qualite}) : révisable"

        return DonneeOfficielle(
            idbank=idbank,
            libelle=libelle_serie,
            valeur=valeur,
            periode=periode,
            unite=unite_serie,
            source="INSEE-BDM",
            date_recuperation=datetime.now().isoformat(),
            revisions=revisions,
            trouve=valeur is not None,
            note=note,
        )

    def _lire_cache(self, idbank, periode) -> Optional[DonneeOfficielle]:
        cur = self.conn.execute(
            "SELECT valeur, libelle, date_recup FROM cache_series "
            "WHERE idbank=? AND periode=?", (idbank, periode))
        row = cur.fetchone()
        if row:
            return DonneeOfficielle(
                idbank=idbank, libelle=row[1], valeur=row[0], periode=periode,
                unite="", source="INSEE-BDM (cache)", date_recuperation=row[2],
                trouve=row[0] is not None, note="Depuis le cache")
        return None

    def _ecrire_cache(self, d: DonneeOfficielle):
        self.conn.execute(
            "INSERT OR REPLACE INTO cache_series "
            "(idbank, periode, valeur, libelle, date_recup, raw_xml) "
            "VALUES (?,?,?,?,?,?)",
            (d.idbank, d.periode, d.valeur, d.libelle, d.date_recuperation, ""))
        self.conn.commit()

    def fermer(self):
        self.conn.close()


# ============================================================================
# MODULE 3 : ORCHESTRATEUR DE MATCHING
# ============================================================================

class Module3MatchingINSEE:
    """
    Pour un claim structuré (régime 1), récupère la donnée officielle INSEE
    correspondante.

    Workflow :
      1. Résoudre indicateur → idbank (avec désambiguïsation)
      2. Détecter la source citée (refuser si non-INSEE)
      3. Récupérer la valeur via le client BDM
      4. Retourner la donnée officielle pour comparaison (Module 4)
    """

    def __init__(self, mode: str = "mock", cache_path: str = "cache_insee.db"):
        # cache_path=":memory:" évite d'écrire un fichier (tests, démos)
        self.client = ClientBDM(mode=mode, cache_path=cache_path)
        self.corresp = CorrespondanceIdbank()

    def matcher(self, claim_id: str, indicateur: str, periode: str,
                phrase: str = "", inclure_revisions: bool = False
                ) -> DonneeOfficielle:
        """Récupère la donnée officielle pour un claim."""
        # 1. Source citée
        source = self.corresp.detecter_source_citee(phrase)
        if source in ("France Travail (DEFM)",):
            return DonneeOfficielle(
                "", "", None, periode, "", source=source, trouve=False,
                note=f"Source citée '{source}' hors périmètre INSEE BIT — "
                     f"comparaison non pertinente")

        # 2. Résolution idbank
        fiche = self.corresp.resoudre(indicateur, phrase)
        if fiche is None:
            return DonneeOfficielle(
                "", "", None, periode, "", trouve=False,
                note=f"Indicateur '{indicateur}' sans correspondance idbank")

        idbank = fiche["principal"]
        if idbank is None:
            return DonneeOfficielle(
                "", fiche.get("libelle", ""), None, periode, "", trouve=False,
                note="Série non disponible dans la BDM pour cet indicateur")

        # 3. Récupération
        donnee = self.client.recuperer(
            idbank, periode, libelle=fiche.get("libelle", ""),
            inclure_revisions=inclure_revisions)
        donnee.unite = fiche.get("unite", donnee.unite)
        return donnee

    def fermer(self):
        self.client.fermer()


# ============================================================================
# TESTS
# ============================================================================

def tests_unitaires():
    print("\n" + "=" * 64)
    print("TESTS UNITAIRES — MODULE 3 : MATCHING INSEE (mode mock)")
    print("=" * 64)

    m3 = Module3MatchingINSEE(mode="mock", cache_path=":memory:")
    erreurs, total = 0, 0

    cas = [
        # (indicateur, periode, phrase, valeur_attendue, libelle_test)
        ("inflation", "2023-07", "l'inflation s'établit à 4,3% selon l'Insee",
         4.3, "Inflation juillet 2023"),
        ("chômage", "2023-Q4", "le taux de chômage atteint 7,5% au T4 selon l'Insee",
         7.5, "Chômage T4 2023"),
        ("PIB", "2024-Q2", "le PIB progresse de 0,2% au 2e trimestre",
         0.2, "PIB T2 2024"),
    ]

    for indic, per, phrase, attendu, libelle in cas:
        total += 1
        d = m3.matcher("TEST", indic, per, phrase)
        ok = d.trouve and abs(d.valeur - attendu) < 0.001
        sym = "✅" if ok else "❌"
        if not ok:
            erreurs += 1
        val = d.valeur if d.valeur is not None else "N/A"
        print(f"{sym} {libelle:25s} → {val} (idbank {d.idbank}) [{d.note}]")

    # Test : déficit en % du PIB → doit être REFUSÉ (pas de série BDM)
    total += 1
    d = m3.matcher("TEST", "déficit", "2023",
                   "le déficit public atteint 5,5% du PIB en 2023")
    if not d.trouve and ("non disponible" in d.note.lower()
                         or "non disponible" in d.libelle.lower()
                         or d.idbank == ""):
        print(f"✅ Déficit en % PIB correctement signalé indisponible en BDM")
    else:
        print(f"❌ Déficit mal géré : {d.note}")
        erreurs += 1

    # Test source non-INSEE refusée
    total += 1
    d = m3.matcher("TEST", "chômage", "2023-Q4",
                   "selon France Travail, 3 millions de demandeurs catégorie A")
    if not d.trouve and "France Travail" in d.note:
        print(f"✅ Source France Travail correctement refusée")
    else:
        print(f"❌ Source non-INSEE mal gérée")
        erreurs += 1

    m3.fermer()
    print(f"\nRésultat : {total - erreurs}/{total} tests passés.")
    print("\n⚠️  RAPPEL : les idbank marqués 'À VÉRIFIER' doivent être confirmés")
    print("    sur insee.fr avant le run de production. Le mode --production")
    print("    nécessite un accès Internet à bdm.insee.fr.")
    return erreurs == 0


if __name__ == "__main__":
    import sys
    mode = "production" if "--production" in sys.argv else "mock"
    if mode == "mock":
        tests_unitaires()
    else:
        # Démo production (nécessite Internet)
        print("Mode production — test sur une série réelle")
        m3 = Module3MatchingINSEE(mode="production")
        d = m3.matcher("DEMO", "inflation", "2023-07",
                       "l'inflation s'établit à 4,3% selon l'Insee")
        print(json.dumps(d.to_dict(), ensure_ascii=False, indent=2))
        m3.fermer()
