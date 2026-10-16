"""
ANALYSE DU CORPUS — produit les chiffres de la Partie II du mémoire
====================================================================

Exécute le pipeline sur TOUT le corpus et calcule, dans l'ordre du mémoire :

  §2.3.1  extraction      : nb de claims, moyenne/médiane/max par article,
                            articles sans claim, densité par média
  §2.3.2  structuration   : claims rattachés à un indicateur, part en %,
                            claims portant sur une variation
  §2.4.1  classification  : régime 1 / régime 2 / indéterminé, régime 1 par
                            indicateur
  §2.5    appariement     : idBank résolus, claims à période infra-annuelle
                            (« directement confrontables »)
  §2.6    cadrage         : événements reconstruits (indicateur dominant ×
                            semaine, ≥ 3 médias), indice de divergence
                            moyen et médian

USAGE (depuis la racine du dépôt)
    python pipeline/analyse_corpus.py data/exemple/corpus_exemple.csv
    python pipeline/analyse_corpus.py mon_corpus.csv --sortie resultats/ \\
        --comparer-memoire

    Options d'analyse de sensibilité :
      --min-medias N            seuil de médias distincts par événement (3)
      --chiffres tous|regime2   chiffres soumis à la mesure de sélection
                                (tous : comportement du pipeline_complet ;
                                 regime2 : seulement les claims de régime 2)
      --verifier-insee mock|production
                                lance M3 + M4 sur les claims de régime 1
                                directement confrontables (verdicts)

SORTIES (dossier --sortie, « resultats/ » par défaut)
    claims.csv       une ligne par claim, avec régime et justification
    evenements.csv   un événement par ligne, avec son indice de divergence
    verdicts.csv     (si --verifier-insee) verdicts M4
    synthese.json    tous les agrégats ci-dessus

⚠️ Les chiffres publiés dans le mémoire (VALEURS_MEMOIRE ci-dessous) ont été
obtenus sur le corpus Europresse de l'auteur, qui n'est pas redistribuable.
Ce script a été écrit après coup (octobre 2026) pour rendre la procédure
rejouable ; l'identité des résultats n'a pas pu être vérifiée. Voir
docs/reproduire_les_resultats.md.
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import re
import statistics
from collections import Counter, defaultdict
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Dict, List, Optional

logging.disable(logging.INFO)

from corpus_io import charger_corpus
from evenements import indicateur_dominant, reconstruire_evenements
from module1_extraction import Module1Extraction
from module2_structuration import Module2Structuration, ClaimCandidat as CC2
from module1_5_classifieur_regime import ClassifieurRegime, Regime
from module3_matching_insee import CorrespondanceIdbank, Module3MatchingINSEE
from module4_validation_revise import (
    Module4Validation, ClaimAValider, DonneeOfficielle as DO4)
from module5_cadrage import Module5Cadrage, ArticleCadrage
from pipeline_complet import valeur_plausible

# Valeurs publiées dans le mémoire (Partie II et Annexe 4), pour comparaison.
VALEURS_MEMOIRE = {
    "articles": 562,
    "claims": 6399,
    "claims_moyenne_par_article": 11.4,
    "claims_mediane_par_article": 10,
    "claims_max_par_article": 81,
    "articles_sans_claim": 14,
    "claims_rattaches_indicateur": 1274,
    "part_unite_pourcentage": 0.64,
    "claims_variation": 575,
    "regime_1": 316,
    "regime_2": 5058,
    "indetermine": 1025,
    "regime_1_inflation": 167,
    "regime_1_chômage": 82,
    "regime_1_PIB": 28,
    "regime_1_déficit": 24,
    "regime_1_dette": 15,
    "idbank_resolus": 292,
    "periode_infra_annuelle": 42,
    "evenements": 27,
    "divergence_moyenne": 0.80,
    "divergence_mediane": 0.81,
}

REGEX_PERIODE_FINE = re.compile(r"^\d{4}-(?:Q[1-4]|\d{2})$")


@dataclass
class LigneClaim:
    article_id: str
    media: str
    date: str
    claim_id: str
    valeur_brute: str
    valeur: Optional[float]
    unite: str
    indicateur_m2: str
    periode: str
    est_variation: bool
    regime: str
    indicateur_officiel: str
    idbank_resolu: bool
    periode_infra_annuelle: bool
    justification: str


def analyser(articles: List[Dict[str, str]], min_medias: int = 3,
             chiffres: str = "tous") -> Dict:
    """Exécute M1 → M2 → M1.5 puis la reconstruction d'événements et M5."""
    m1, m2, clf, m5 = (Module1Extraction(), Module2Structuration(),
                       ClassifieurRegime(), Module5Cadrage())

    lignes: List[LigneClaim] = []
    claims_par_article: Dict[str, int] = {}
    non_structures = 0
    articles_annotes = []
    chiffres_par_article: Dict[str, List[str]] = {}

    for art in articles:
        claims = m1.extraire(art["texte"], art["id"])
        claims_par_article[art["id"]] = len(claims)
        cands = [CC2(c.claim_id, c.phrase, c.valeur_brute) for c in claims]
        structs = {s.claim_id: s for s in m2.structurer(cands, art["date"])}
        non_structures += len(claims) - len(structs)

        indicateurs_art = []
        chiffres_regime2 = []
        for c in claims:
            s = structs.get(c.claim_id)
            if s is None:
                # valeur non convertible : non classée (comptée à part)
                continue
            reg = clf.classer(s.claim_id, s.phrase_originale, s.indicateur,
                              s.unite, s.est_variation, s.modificateur,
                              date_article=art["date"])
            indicateurs_art.append(s.indicateur)
            ind_off = reg.indicateur_officiel
            fiche = CorrespondanceIdbank.resoudre(ind_off, s.phrase_originale) \
                if ind_off else None
            idbank_ok = bool(fiche and fiche.get("principal"))
            lignes.append(LigneClaim(
                article_id=art["id"], media=art["media"], date=art["date"],
                claim_id=s.claim_id, valeur_brute=c.valeur_brute,
                valeur=s.valeur, unite=s.unite, indicateur_m2=s.indicateur,
                periode=s.periode, est_variation=s.est_variation,
                regime=reg.regime.value, indicateur_officiel=ind_off,
                idbank_resolu=idbank_ok,
                periode_infra_annuelle=bool(REGEX_PERIODE_FINE.match(s.periode)),
                justification=reg.justification,
            ))
            if reg.regime == Regime.FAIBLE:
                chiffres_regime2.append(c.valeur_brute)

        chiffres_par_article[art["id"]] = (
            [c.valeur_brute for c in claims] if chiffres == "tous"
            else chiffres_regime2)
        articles_annotes.append({**art, "indicateur_dominant":
                                 indicateur_dominant(indicateurs_art)})

    # ---- §2.6 : événements et cadrage ----
    par_id = {a["id"]: a for a in articles}
    evenements = reconstruire_evenements(articles_annotes, min_medias=min_medias)
    lignes_evt = []
    for evt in evenements:
        arts = [ArticleCadrage(i, par_id[i]["media"], par_id[i]["titre"],
                               par_id[i]["texte"], par_id[i]["date"],
                               chiffres_par_article[i])
                for i in evt.article_ids]
        analyse = m5.analyser_evenement(
            evt.cle, arts,
            mots_cles_evenement=Module2Structuration.INDICATEURS_KEYWORDS[evt.indicateur])
        lignes_evt.append({
            "evenement": evt.cle, "indicateur": evt.indicateur,
            "semaine": evt.semaine, "n_medias": evt.n_medias,
            "n_articles": len(evt.article_ids),
            "n_articles_pertinents": analyse.n_pertinents,
            "medias": " | ".join(evt.medias),
            "n_chiffres_univers": len(set().union(
                *[set(sg.chiffres_cites) for sg in analyse.signatures])) if analyse.signatures else 0,
            "chiffres_consensuels": " | ".join(analyse.chiffres_consensuels),
            "indice_divergence": analyse.indice_divergence,
        })

    return {
        "lignes": lignes,
        "evenements": lignes_evt,
        "synthese": _synthese(articles, lignes, claims_par_article,
                              non_structures, lignes_evt, min_medias, chiffres),
    }


def _synthese(articles, lignes, claims_par_article, non_structures,
              lignes_evt, min_medias, chiffres) -> Dict:
    n_claims = sum(claims_par_article.values())
    par_regime = Counter(l.regime for l in lignes)
    r1 = [l for l in lignes if l.regime == Regime.FORTE.value]
    r1_par_ind = Counter(l.indicateur_officiel for l in r1)
    r1_resolus = [l for l in r1 if l.idbank_resolu]
    densites = list(claims_par_article.values()) or [0]
    media_de = {a["id"]: a["media"] for a in articles}
    claims_media, articles_media = Counter(), Counter()
    for aid, n in claims_par_article.items():
        claims_media[media_de[aid]] += n
        articles_media[media_de[aid]] += 1
    divergences = [e["indice_divergence"] for e in lignes_evt]

    return {
        "parametres": {"min_medias": min_medias, "chiffres_selection": chiffres},
        "articles": len(articles),
        "claims": n_claims,
        "claims_non_structures": non_structures,
        "claims_moyenne_par_article": round(statistics.mean(densites), 1),
        "claims_mediane_par_article": statistics.median(densites),
        "claims_max_par_article": max(densites),
        "articles_sans_claim": sum(1 for n in densites if n == 0),
        "densite_par_media": {m: round(claims_media[m] / articles_media[m], 1)
                              for m in sorted(articles_media)},
        "claims_rattaches_indicateur": sum(1 for l in lignes
                                           if l.indicateur_m2 != "inconnu"),
        "part_unite_pourcentage": round(
            sum(1 for l in lignes if l.unite == "%") / len(lignes), 2) if lignes else 0.0,
        "claims_variation": sum(1 for l in lignes if l.est_variation),
        "regime_1": par_regime.get(Regime.FORTE.value, 0),
        "regime_2": par_regime.get(Regime.FAIBLE.value, 0),
        "indetermine": par_regime.get(Regime.INDETERMINE.value, 0),
        **{f"regime_1_{ind}": r1_par_ind.get(ind, 0)
           for ind in ("inflation", "chômage", "PIB", "déficit", "dette")},
        "idbank_resolus": len(r1_resolus),
        "periode_infra_annuelle": sum(1 for l in r1_resolus
                                      if l.periode_infra_annuelle),
        "evenements": len(lignes_evt),
        "divergence_moyenne": round(statistics.mean(divergences), 2) if divergences else None,
        "divergence_mediane": round(statistics.median(divergences), 2) if divergences else None,
    }


def verifier_insee(lignes: List[LigneClaim], mode: str) -> List[Dict]:
    """M3 + M4 sur les claims de régime 1 directement confrontables."""
    m3 = Module3MatchingINSEE(mode=mode,
                              cache_path="cache_insee.db" if mode == "production" else ":memory:")
    m4 = Module4Validation()
    sorties = []
    try:
        for l in lignes:
            if not (l.regime == Regime.FORTE.value and l.idbank_resolu
                    and l.periode_infra_annuelle and l.unite == "%"
                    and not l.est_variation and l.valeur is not None
                    and valeur_plausible(l.indicateur_officiel, l.valeur)):
                continue
            d = m3.matcher(l.claim_id, l.indicateur_officiel, l.periode)
            res = m4.valider(
                ClaimAValider(l.claim_id, l.valeur, l.valeur_brute,
                              l.indicateur_officiel, l.unite),
                DO4(l.indicateur_officiel, d.valeur, l.periode, d.unite,
                    trouve=d.trouve))
            sorties.append({
                "claim_id": l.claim_id, "media": l.media, "date": l.date,
                "indicateur": l.indicateur_officiel, "periode": l.periode,
                "valeur_citee": l.valeur, "valeur_insee": d.valeur,
                "source": d.source, "verdict": res.verdict.value,
                "ecart_absolu": res.ecart_absolu, "note_insee": d.note,
            })
    finally:
        m3.fermer()
    return sorties


def _ecrire_csv(chemin: Path, lignes: List[Dict]) -> None:
    if not lignes:
        chemin.write_text("", encoding="utf-8")
        return
    with open(chemin, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(lignes[0]), delimiter=";")
        w.writeheader()
        w.writerows(lignes)


def rapport(s: Dict, comparer: bool = False) -> str:
    """Rapport texte dans l'ordre du mémoire."""
    def ligne(libelle, cle, fmt="{}"):
        val = s.get(cle)
        txt = fmt.format(val) if val is not None else "n/a"
        if comparer and cle in VALEURS_MEMOIRE:
            txt = f"{txt:>10}   (mémoire : {VALEURS_MEMOIRE[cle]})"
        return f"  {libelle:46s}{txt}"

    n = s["claims"] or 1
    L = ["=" * 78, "ANALYSE DU CORPUS — chiffres de la Partie II", "=" * 78,
         ligne("Articles", "articles"),
         "", "§2.3.1 Extraction",
         ligne("Claims extraits (M1)", "claims"),
         ligne("Moyenne / article", "claims_moyenne_par_article"),
         ligne("Médiane / article", "claims_mediane_par_article"),
         ligne("Maximum / article", "claims_max_par_article"),
         ligne("Articles sans claim", "articles_sans_claim"),
         "  Densité par média : " + ", ".join(
             f"{m} {d}" for m, d in s["densite_par_media"].items()),
         "", "§2.3.2 Structuration",
         ligne("Claims non convertibles (non classés)", "claims_non_structures"),
         ligne("Claims rattachés à un indicateur", "claims_rattaches_indicateur"),
         ligne("Part exprimée en %", "part_unite_pourcentage"),
         ligne("Claims portant sur une variation", "claims_variation"),
         "", "§2.4.1 Classification en régimes",
         ligne(f"Régime 1 ({100 * s['regime_1'] / n:.0f} %)", "regime_1"),
         ligne(f"Régime 2 ({100 * s['regime_2'] / n:.0f} %)", "regime_2"),
         ligne(f"Indéterminé ({100 * s['indetermine'] / n:.0f} %)", "indetermine"),
         ligne("  dont régime 1 inflation", "regime_1_inflation"),
         ligne("  dont régime 1 chômage", "regime_1_chômage"),
         ligne("  dont régime 1 PIB", "regime_1_PIB"),
         ligne("  dont régime 1 déficit", "regime_1_déficit"),
         ligne("  dont régime 1 dette", "regime_1_dette"),
         "", "§2.5 Appariement INSEE",
         ligne("idBank résolus (régime 1)", "idbank_resolus"),
         ligne("dont période mois/trimestre", "periode_infra_annuelle"),
         "", "§2.6 Cadrage inter-médias",
         ligne("Événements (≥ min_medias médias)", "evenements"),
         ligne("Indice de divergence moyen", "divergence_moyenne"),
         ligne("Indice de divergence médian", "divergence_mediane"),
         "=" * 78]
    return "\n".join(L)


def main(argv: Optional[List[str]] = None) -> Dict:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    p.add_argument("corpus", help="CSV id;media;date;titre;texte")
    p.add_argument("--sortie", default="resultats", help="dossier de sortie")
    p.add_argument("--min-medias", type=int, default=3)
    p.add_argument("--chiffres", choices=("tous", "regime2"), default="tous")
    p.add_argument("--verifier-insee", choices=("mock", "production"))
    p.add_argument("--comparer-memoire", action="store_true",
                   help="affiche en regard les valeurs publiées dans le mémoire")
    args = p.parse_args(argv)

    articles = charger_corpus(args.corpus)
    res = analyser(articles, min_medias=args.min_medias, chiffres=args.chiffres)

    sortie = Path(args.sortie)
    sortie.mkdir(parents=True, exist_ok=True)
    _ecrire_csv(sortie / "claims.csv", [asdict(l) for l in res["lignes"]])
    _ecrire_csv(sortie / "evenements.csv", res["evenements"])
    if args.verifier_insee:
        verdicts = verifier_insee(res["lignes"], args.verifier_insee)
        _ecrire_csv(sortie / "verdicts.csv", verdicts)
        res["synthese"]["verdicts"] = dict(Counter(v["verdict"] for v in verdicts))
    with open(sortie / "synthese.json", "w", encoding="utf-8") as f:
        json.dump(res["synthese"], f, ensure_ascii=False, indent=2)

    print(rapport(res["synthese"], comparer=args.comparer_memoire))
    if args.verifier_insee:
        print(f"Verdicts M4 ({args.verifier_insee}) : {res['synthese']['verdicts']}")
    print(f"Fichiers écrits dans {sortie}/")
    return res


if __name__ == "__main__":
    main()
