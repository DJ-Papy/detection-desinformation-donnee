"""Bout en bout sur le corpus fictif d'exemple (data/exemple/corpus_exemple.csv).

Ces valeurs verrouillent le comportement actuel : si une modification du
code les fait bouger, c'est volontaire (et la doc doit suivre) ou c'est une
régression.
"""

import analyse_corpus
import pipeline_complet
from corpus_io import charger_corpus
from conftest import CORPUS_EXEMPLE


def test_lecture_du_corpus():
    articles = charger_corpus(CORPUS_EXEMPLE)
    assert len(articles) == 10
    assert set(articles[0]) >= {"id", "media", "date", "titre", "texte"}


def test_analyse_corpus_exemple(tmp_path):
    res = analyse_corpus.main([str(CORPUS_EXEMPLE), "--sortie", str(tmp_path),
                               "--verifier-insee", "mock"])
    s = res["synthese"]
    assert (s["articles"], s["claims"], s["articles_sans_claim"]) == (10, 19, 1)
    assert (s["regime_1"], s["regime_2"], s["indetermine"]) == (10, 6, 3)
    assert s["regime_1"] + s["regime_2"] + s["indetermine"] == s["claims"]
    assert (s["idbank_resolus"], s["periode_infra_annuelle"]) == (10, 7)
    assert s["evenements"] == 2
    assert s["divergence_moyenne"] == 0.82
    assert s["verdicts"] == {"confirmé": 5, "approximatif": 1}
    for f in ("claims.csv", "evenements.csv", "verdicts.csv", "synthese.json"):
        assert (tmp_path / f).exists()


def test_pipeline_complet_demo():
    res = pipeline_complet.main([])   # événement par défaut : chômage T3 2023
    verdicts = sorted(fc["verdict"] for fc in res.factcheck)
    assert verdicts == ["approximatif", "confirmé", "confirmé", "confirmé"]
    assert res.analyse_cadrage.n_pertinents == 4
