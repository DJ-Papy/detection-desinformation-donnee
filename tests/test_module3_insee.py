"""Module 3 — appariement INSEE (sans réseau : mode mock et parseur SDMX)."""

import pytest

from module3_matching_insee import ClientBDM, CorrespondanceIdbank, Module3MatchingINSEE


@pytest.fixture
def m3():
    m = Module3MatchingINSEE(mode="mock", cache_path=":memory:")
    yield m
    m.fermer()


@pytest.mark.parametrize("indicateur, periode, attendu, idbank", [
    ("inflation", "2023-07", 4.3, "011814632"),
    ("chômage", "2023-Q4", 7.5, "001688527"),
    ("PIB", "2024-Q2", 0.2, "011794844"),
])
def test_mock(m3, indicateur, periode, attendu, idbank):
    d = m3.matcher("T", indicateur, periode, "selon l'Insee")
    assert d.trouve and d.valeur == attendu and d.idbank == idbank


def test_deficit_en_pct_du_pib_sans_serie_bdm(m3):
    d = m3.matcher("T", "déficit", "2023", "le déficit public atteint 5,5% du PIB")
    assert not d.trouve and "non disponible" in d.note


def test_source_france_travail_refusee(m3):
    d = m3.matcher("T", "chômage", "2023-Q4", "selon France Travail, 3 millions de demandeurs")
    assert not d.trouve and "France Travail" in d.note


def test_mock_n_ecrit_pas_dans_le_cache(tmp_path):
    """Non-régression du correctif d'octobre 2026."""
    cache = tmp_path / "cache.db"
    mock = ClientBDM(mode="mock", cache_path=str(cache))
    mock.recuperer("001688527", "2023-Q4")
    mock.fermer()
    prod = ClientBDM(mode="production", cache_path=str(cache))
    assert prod._lire_cache("001688527", "2023-Q4") is None
    prod.fermer()


XML_SDMX = """<?xml version="1.0" encoding="UTF-8"?>
<message:StructureSpecificData xmlns:message="http://www.sdmx.org/resources/sdmxml/schemas/v2_1/message">
  <message:DataSet>
    <Series IDBANK="001688527" TITLE_FR="Taux de chômage au sens du BIT" UNIT_MEASURE="POURCENT" DECIMALS="1">
      <Obs TIME_PERIOD="2023-Q4" OBS_VALUE="7.5" OBS_STATUS="A" OBS_QUAL="DEF"/>
      <Obs TIME_PERIOD="2023-Q3" OBS_VALUE="7.4" OBS_STATUS="A" OBS_QUAL="PROV"/>
    </Series>
  </message:DataSet>
</message:StructureSpecificData>"""


def test_parseur_sdmx_structure_specific():
    client = ClientBDM(mode="production", cache_path=":memory:")
    d = client._parser_sdmx(XML_SDMX, "001688527", "2023-Q4", "", inclure_revisions=False)
    assert d.trouve and d.valeur == 7.5 and d.unite == "POURCENT" and d.note == ""
    d = client._parser_sdmx(XML_SDMX, "001688527", "2023-Q3", "", inclure_revisions=False)
    assert d.valeur == 7.4 and "non définitive" in d.note
    d = client._parser_sdmx(XML_SDMX, "001688527", "2022-Q1", "", inclure_revisions=False)
    assert not d.trouve
    client.fermer()


def test_correspondance_idbank():
    assert CorrespondanceIdbank.resoudre("chômage")["principal"] == "001688527"
    assert CorrespondanceIdbank.resoudre("déficit")["principal"] is None
    assert CorrespondanceIdbank.resoudre("population") is None
