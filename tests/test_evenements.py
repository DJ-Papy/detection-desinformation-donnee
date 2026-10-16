"""Reconstruction des événements (indicateur dominant × semaine ISO, ≥ 3 médias)."""

from evenements import indicateur_dominant, reconstruire_evenements, semaine_iso


def test_indicateur_dominant():
    assert indicateur_dominant(["inflation", "chômage", "inflation", "inconnu"]) == "inflation"
    assert indicateur_dominant(["inconnu", "inconnu"]) == ""
    # égalité : ordre du lexique du module 2 (chômage avant inflation)
    assert indicateur_dominant(["inflation", "chômage"]) == "chômage"


def test_semaine_iso():
    assert semaine_iso("2023-11-15") == "2023-W46"
    assert semaine_iso("2024-12-30") == "2025-W01"   # semaine ISO à cheval sur deux années
    assert semaine_iso("") is None


def _art(i, media, date, indic="chômage"):
    return {"id": i, "media": media, "date": date, "indicateur_dominant": indic}


def test_seuil_de_trois_medias_distincts():
    arts = [_art("1", "A", "2023-11-15"), _art("2", "A", "2023-11-16"),
            _art("3", "B", "2023-11-16")]
    assert reconstruire_evenements(arts, min_medias=3) == []   # 2 médias seulement
    arts.append(_art("4", "C", "2023-11-17"))
    (evt,) = reconstruire_evenements(arts, min_medias=3)
    assert evt.cle == "chômage 2023-W46" and evt.medias == ["A", "B", "C"]
    assert len(evt.article_ids) == 4   # deux articles du média A conservés


def test_coupure_hebdomadaire():
    # Limite L8 : dimanche et lundi tombent dans deux semaines différentes
    arts = [_art("1", "A", "2023-11-19"), _art("2", "B", "2023-11-20"),
            _art("3", "C", "2023-11-20")]
    assert reconstruire_evenements(arts, min_medias=3) == []
