# Reproduire les résultats du mémoire

## Où en est la reproductibilité

| Élément | Disponible ? | Commentaire |
|---|---|---|
| Règles du pipeline | oui | Décrites au §2.2 à §2.6 du mémoire, implémentées en v2.0.0 |
| Code exact ayant produit les chiffres | **non** | Non conservé. La v2.0.0 est une réécriture d'après le texte (octobre 2026) |
| Corpus (562 articles) | **non** | Articles Europresse sous droits ; non redistribuables |
| Données INSEE | oui | API publique, sans compte |
| Chiffres publiés | oui | Repris dans `pipeline/analyse_corpus.py` (`VALEURS_MEMOIRE`) |

Conséquence : **personne, auteur compris, ne peut aujourd'hui vérifier que la v2.0.0 redonne exactement 6 399 / 316 / 27 / 0,80.** Ce que le dépôt permet, c'est de rejouer la procédure sur un corpus reconstitué et de mesurer l'écart.

## Rejouer la procédure

### 1. Reconstituer le corpus

Paramètres du mémoire (§2.2.1) :

- Base : Europresse, accès bibliothèque universitaire.
- Titres : *Le Monde*, *Les Échos*, *Le Figaro*, *Libération*, *L'Obs*, *Le Point*, AFP.
- Période : janvier 2023 à décembre 2024.
- Thèmes : chômage, inflation, croissance, dette et déficit publics.
- Volume obtenu : 50 exports PDF, 755 articles bruts, 562 après déduplication (Annexe 4).

Placer les exports dans `data/corpus/` (exclu de Git), puis :

```bash
python pipeline/outil_corpus_stats.py data/corpus/ data/corpus/rapport.json data/corpus/corpus.csv
```

Contrôles à faire avant d'aller plus loin : répartition par média (Le Monde 102, Les Échos 96, Le Figaro 91, Libération 83, L'Obs 69, Le Point 63, AFP 58) et par année (294 en 2023, 268 en 2024).

### 2. Lancer l'analyse et comparer

```bash
python pipeline/analyse_corpus.py data/corpus/corpus.csv --sortie resultats/ --comparer-memoire
```

Chaque agrégat est affiché à côté de la valeur publiée.

### 3. Interpréter les écarts

Un écart peut venir du corpus (articles différents) ou des choix de reconstruction ci-dessous. Les seconds sont paramétrables ou isolés dans le code pour pouvoir être testés.

## Choix faits lors de la reconstruction

| Point | Ce que dit le mémoire | Ce que fait le code v2.0.0 | Où le modifier |
|---|---|---|---|
| Fin d'article (M0) | Troncature au « pied de page de copyright Europresse » | Première occurrence de `© AAAA`, « Le présent document est protégé… » ou « Certificat émis le » | `EuropressePagePattern.REGEX_FIN_ARTICLE` |
| Nom de média (M0) | « Corrigé par normalisation » | Recherche d'un titre connu, sinon code source de l'identifiant (seul `AFPD` est renseigné), sinon valeur brute | `MEDIAS_CANONIQUES`, `CODES_SOURCE_EUROPRESSE` |
| Doublons (M0) | Version au taux d'extraction « le plus proche de l'optimum » | Plus petit écart à 1 entre mots extraits et mots annoncés | `AnalyseurCorpus._ecart_optimum` |
| Pays étranger (M1.5) | « Pays étranger sans source française » | Liste fermée de 20 pays ou zones ; neutralisée par « France », « français », « hexagone », « Insee » | `REGEX_PAYS_ETRANGER`, `REGEX_MARQUEUR_FRANCE` |
| Année future (M1.5) | « Références à une année future » | Année mentionnée > année de l'article | `classer(..., date_article=...)` |
| Ratio du PIB (M1.5) | « Ratios exprimés en % du PIB confondus avec le taux de croissance » | Nombre + « % / points du PIB » : l'indicateur PIB est retiré, les autres restent | `REGEX_RATIO_PIB` |
| Rattachement (M2) | 1 274 claims « rattachés à un indicateur » | Indicateur du module 2 différent de `inconnu` | `analyse_corpus._synthese` |
| idBank résolus (M3) | 292 sur 316 | Claims de régime 1 dont l'indicateur a une série principale (le déficit n'en a pas) | idem |
| Période fine (M3) | ≈ 42 claims « citent un mois ou un trimestre » | Période au format `AAAA-MM` ou `AAAA-Qn` parmi les idBank résolus | `REGEX_PERIODE_FINE` |
| Indicateur dominant (événements) | « Indicateur dominant » | Indicateur le plus fréquent parmi les claims de l'article, hors `inconnu` ; égalité : ordre du lexique | `evenements.indicateur_dominant` |
| Semaine (événements) | « Semaine de publication » | Semaine ISO 8601 | `evenements.semaine_iso` |
| Seuil (événements) | « Au moins trois médias distincts » | Idem | `--min-medias` |
| Chiffres comparés (M5) | « L'ensemble des chiffres disponibles pour un événement » | Tous les claims extraits de chaque article | `--chiffres tous|regime2` |
| Filtre de pertinence (M5) | — | Mots-clés du module 2 pour l'indicateur de l'événement | `analyse_corpus.analyser` |

Les cohérences internes vérifiables sans corpus sont respectées : 316 − 24 claims de déficit (sans série BDM) = 292 idBank résolus.

## Si le corpus d'origine est retrouvé

Le CSV utilisé pour le mémoire (562 articles, format `id|media|date|titre|texte`) suffit. Dans ce cas :

1. lancer l'étape 2 ci-dessus ;
2. reporter le tableau de comparaison dans ce document, avec la date et le commit utilisé ;
3. si les chiffres diffèrent, documenter l'écart plutôt que d'ajuster le code pour retomber sur les valeurs publiées.
