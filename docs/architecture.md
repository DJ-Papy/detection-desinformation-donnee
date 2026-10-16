# Architecture du pipeline

Chaque module est un fichier Python autonome dans `pipeline/`, testable seul (`python pipeline/moduleX.py` lance ses tests intégrés ou une démonstration). Les modules s'importent par leur nom de fichier : lancez les scripts depuis la racine du dépôt (`python pipeline/xxx.py`).

## Flux de données

```text
PDF Europresse
  │  M0  EuropresseParser.parser(pdf)                → list[ArticleEuropresse]
  ▼
Corpus CSV (id ; media ; date ; titre ; texte)      ← corpus_io.charger_corpus()
  │  M1  Module1Extraction.extraire(texte, id)       → list[ClaimCandidat]
  │  M2  Module2Structuration.structurer(c, date)    → list[ClaimStructure]
  │  M1.5 ClassifieurRegime.classer(…, date_article) → RegimeVerifiabilite
  ├── régime 1
  │     M3  Module3MatchingINSEE.matcher(…)          → DonneeOfficielle
  │     M4  Module4Validation.valider(claim, donnée)  → ResultatValidation
  └── tous les articles
        evenements.reconstruire_evenements(…)        → list[Evenement]
        M5  Module5Cadrage.analyser_evenement(…)      → AnalyseCadrage
```

L'ordre M2 → M1.5 dans le code diffère de la numérotation : le classifieur utilise l'unité et l'indicateur produits par le module 2. Le mémoire explique la numérotation 1.5 (§2.1.2) : ce module n'ajoute pas un traitement mais une décision d'aiguillage.

## Module 0 — `module0_parser_europresse.py`

| | |
|---|---|
| Entrée | export PDF Europresse (plusieurs articles par fichier) |
| Sortie | `ArticleEuropresse` : `article_id` (identifiant Europresse `news·AAAAMMJJ·SOURCE·…`), `source_media` (normalisé), `source_media_brut`, `date_publication`, `titre`, `texte`, `mots_revendiques`, `mots_extraits`, `warnings` |
| Méthode | segmentation par la taille de police du titre (16 à 30 pt) et la présence de l'identifiant ; métadonnées lues au-dessus du titre ; colonnes détectées par regroupement des abscisses de début de ligne ; recollage des césures ; troncature au pied de page de copyright |
| Contrôle | `taux_extraction` = mots extraits / mots annoncés ; alerte si < 0,7 ou > 1,3 |
| Ligne de commande | `python pipeline/module0_parser_europresse.py export.pdf [sortie.csv]` (diagnostic, puis export) |

Les seuils typographiques sont regroupés dans `EuropressePagePattern` : si Europresse change sa mise en page, c'est le seul endroit à modifier.

`outil_corpus_stats.py` applique le module 0 à un dossier entier, déduplique par identifiant (version au meilleur taux d'extraction) et écrit le corpus CSV.

## Module 1 — `module1_extraction.py`

| | |
|---|---|
| Entrée | texte d'un article |
| Sortie | `ClaimCandidat` : `claim_id`, `phrase`, `valeur_brute` (« 7,3 % »), positions |
| Méthode | découpage en phrases (ponctuation **et** retours à la ligne) ; six motifs essayés dans l'ordre : pourcentage décimal, pourcentage entier, milliards/millions, points, montant en euros, entier à séparateur de milliers ; le **premier** motif retenu par phrase |
| Exclusions | « article n », « page n », « chapitre n », années (voir limite L1) |

## Module 2 — `module2_structuration.py`

| | |
|---|---|
| Entrée | `ClaimCandidat` + date de l'article |
| Sortie | `ClaimStructure` : `valeur` (float), `unite` (`%`, `milliards €`, `millions`, `points`, `€`, `effectif`, `indéterminée`), `indicateur` (`chômage`, `PIB`, `inflation`, `dette`, `population`, `salaire`, `inconnu`), `periode` (`2023-Q4`, `2023-12`, `2023`), `modificateur`, `est_variation` |
| Méthode | lexique de mots-clés par indicateur (score = nombre de mots-clés présents) ; période : trimestre, puis mois, puis année, puis repli sur l'année de l'article |

Les mots-clés du déficit sont rattachés à l'indicateur `dette` ; c'est le module 1.5 qui distingue le déficit.

## Module 1.5 — `module1_5_classifieur_regime.py`

| | |
|---|---|
| Entrée | phrase, indicateur et unité du module 2, date de l'article |
| Sortie | `RegimeVerifiabilite` : `regime` (`FORTE`, `FAIBLE`, `INDETERMINE`), `score_confiance`, `indicateur_officiel`, `marqueurs_detectes`, `justification` |

Ordre des règles (la première qui s'applique décide) :

1. Pays étranger sans marqueur français → régime 2
2. Année postérieure à l'article → régime 2
3. Marqueur de prévision, sauf constat attribué à une source officielle → régime 2
4. Indicateur officiel + source officielle → régime 1
5. Prévision + grandeur budgétaire → régime 2
6. Indicateur officiel et score régime 1 > score régime 2 → régime 1
7. Grandeur budgétaire sans indicateur → régime 2
8. Score régime 2 > score régime 1 → régime 2 ; score régime 1 > score régime 2 sans indicateur → indéterminé ; égalité → indéterminé

Scores : régime 1 = 2 × indicateur + 2 × source + 1 × verbe de constat + 0,5 × unité « % » ; régime 2 = 2 × prévision + 1 × acteur politique + 1 × grandeur budgétaire. Avant tout, la mention « X % du PIB » retire l'indicateur PIB.

## Module 3 — `module3_matching_insee.py`

| | |
|---|---|
| Entrée | indicateur, période, phrase |
| Sortie | `DonneeOfficielle` : `idbank`, `libelle`, `valeur`, `periode`, `unite`, `source`, `trouve`, `note`, `revisions` |
| Modes | `mock` (valeurs saisies à la main, sans réseau, sans cache) ; `production` (API SDMX de la BDM, cache SQLite `cache_insee.db`, 0,5 s entre deux requêtes) |
| Refus | source citée France Travail / Pôle emploi / catégorie A ; indicateur sans série (déficit) |

Table des séries : [`idbank_insee.md`](idbank_insee.md).

## Module 4 — `module4_validation_revise.py`

| | |
|---|---|
| Entrée | `ClaimAValider` (valeur citée, texte brut, indicateur) + `DonneeOfficielle` |
| Sortie | `ResultatValidation` : `verdict`, écarts absolu et relatif, seuil appliqué et ses composantes, `justification` |

Seuil « confirmé » *s* = max(demi-unité du dernier chiffre écrit par le journaliste, incertitude INSEE de l'indicateur), élargi en cas de modificateur (« environ » : 5 % de la valeur officielle). Verdict selon l'écart absolu *e* : confirmé si *e* ≤ *s* ; approximatif si *e* ≤ 2,5 *s* ; imprécis si *e* ≤ 5 *s* ; incorrect au-delà. Un claim signalé comme provisoire (« estimation flash ») est atténué d'un cran.

## Événements — `evenements.py`

| | |
|---|---|
| Entrée | articles avec `id`, `media`, `date`, `indicateur_dominant` |
| Sortie | `Evenement` : `cle` (« chômage 2023-W46 »), `indicateur`, `semaine`, `article_ids`, `medias` |
| Paramètre | `min_medias` (3) |

## Module 5 — `module5_cadrage.py`

| | |
|---|---|
| Entrée | `ArticleCadrage` (texte + chiffres cités) pour un événement, mots-clés de pertinence |
| Sortie | `AnalyseCadrage` : `indice_divergence`, `chiffres_consensuels`, `chiffres_clivants`, `signatures` par article (chiffres cités et exclusifs, taux de couverture, scores Entman, acteurs) |

Les chiffres sont normalisés (« 5,5 % », « 5,5% » → `5.5%` ; « 10 milliards » → `10Md`). Indice de divergence = nombre de chiffres cités par un seul article / nombre de chiffres distincts de l'événement. Voir la limite L9 sur son interprétation.

## Orchestrateurs

| Script | Usage |
|---|---|
| `pipeline_complet.py` | un événement : tableau de fact-checking + analyse de cadrage (`--help` pour les options) |
| `analyse_corpus.py` | tout le corpus : agrégats de la Partie II, `claims.csv`, `evenements.csv`, `synthese.json`, `verdicts.csv` en option |
| `outil_corpus_stats.py` | dossier de PDF → corpus dédupliqué + statistiques descriptives |
| `verifier_api_insee.py` | contrôle des quatre séries INSEE en conditions réelles |
