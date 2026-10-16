# Limites connues

Ce document recense les limites du pipeline, distingue celles que le mémoire reconnaît déjà de celles repérées en préparant la publication (octobre 2026), et indique pour chacune l'effet probable sur les chiffres publiés.

**Règle suivie** : les défauts des modules 1, 2 et 5 n'ont pas été corrigés dans la version 2.0.0, pour que le code reste celui qui décrit les résultats du mémoire. Chaque limite testable est écrite comme un test `xfail` strict dans `tests/` : il échoue tant que la limite existe et pytest signale le jour où un correctif la fait passer.

## Synthèse : quels chiffres du mémoire sont fragiles ?

| Chiffre publié | Limites en cause | Effet probable |
|---|---|---|
| 6 399 claims | L1, L2 | Indéterminé : L1 en retire, L2 en ajoute |
| 316 en régime 1 (5 %) | V1, L1, L2, L3 | Probablement **sous-estimé** (L1 retire des chiffres datés, L2 ampute le contexte) ; ampleur inconnue |
| ≈ 42 directement confrontables (≈ 1 %) | L1, L4 | Indéterminé : L1 en retire, L4 crée de fausses périodes « mai » |
| 27 événements | L8 | Dépend des paramètres ; non stabilisé |
| Divergence 0,80 | L9 | Probablement **surestimée** comme mesure de choix éditorial |

La conclusion qualitative du mémoire (le régime 1 est très minoritaire) n'est pas menacée par ces limites. Les pourcentages exacts et l'interprétation de l'indice de divergence le sont davantage.

---

## A. Limites reconnues dans le mémoire

### V1 — Classifieur non validé (§2.4.2)
Le partage entre régimes repose sur des règles dont le taux d'erreur n'a pas été mesuré. Le protocole (≈ 100 claims, double codage en aveugle, κ de Cohen) est décrit au §2.4.2 et le guide de codage en Annexe 3, mais il n'a pas été exécuté.
**Pour la lever** : `analyse_corpus.py` écrit `resultats/claims.csv` (une ligne par claim, avec la décision et sa justification) ; tirer un échantillon aléatoire, masquer les colonnes `regime` et `justification`, faire coder par deux personnes, puis calculer κ.

### V2 — Repli de la période sur l'année de l'article (§2.3.2)
Sans mention explicite, un chiffre reçoit l'année de publication, sans que ce repli soit signalé. Exemple du corpus fictif : la dette de 2023 publiée en mars 2024 reçoit la période « 2024 ».

### V3 — Marges d'incertitude INSEE à confirmer (module 4)
Les valeurs de `IC_INSEE` (chômage ± 0,3 point, inflation ± 0,1, PIB ± 0,2, dette et déficit ± 0,1) sont des estimations de départ, pas des valeurs relevées dans les notes méthodologiques de l'INSEE. Elles fixent le seuil du verdict « confirmé ».

### V4 — Marqueurs Entman interprétatifs (§2.6, Annexe 2)
Repérage lexical aveugle au sens, à la négation et à l'ironie, sans lemmatisation (« condamner » ne capte pas « condamne »). Certains marqueurs sont très génériques (« doit », « politique », « mesure ») et « politique » figure dans deux fonctions. En cas d'égalité, la fonction dominante est la première dans l'ordre du codebook. Mesure secondaire : elle n'entre pas dans l'indice de divergence.

### V5 — Périmètre (§2.7)
Presse écrite, indicateurs macroéconomiques, 2023-2024 : c'est le cas *le plus favorable* à la vérification. Le pipeline ne mesure pas l'intention ; il ne détecte donc pas la désinformation au sens de Wardle et Derakhshan (2017), mais des écarts chiffrés et des différences de sélection.

---

## B. Limites repérées en préparant la publication

### L1 — Un chiffre suivi d'une année est écarté (module 1) · `xfail`
`Module1Extraction._est_exclusion` cherche une année (`19xx` ou `20xx`) dans une fenêtre de **20 caractères autour** du chiffre extrait, et non dans le chiffre lui-même. « Le PIB progresse de 0,9 % en 2023 » ne produit donc aucun claim, de même que « 5 % d'ici 2027 ».
**Effet** : retire de l'univers les chiffres datés (souvent les plus vérifiables) et une partie des projections. Le test 4 du module, qui attend au moins 4 claims, en obtient 3.
**Correctif proposé** : appliquer le motif d'exclusion à `match.group(0)` seulement.

### L2 — Un retour à la ligne vaut fin de phrase (module 1) · `xfail`
`_decouper_phrases` coupe aux points **et** aux retours à la ligne. Le texte produit par le module 0 conserve les lignes des colonnes Europresse : si le corpus a été analysé sous cette forme, une « phrase » est en réalité une ligne imprimée d'une quarantaine de caractères.
**Effet** : le contexte vu par les modules 2 et 1.5 est amputé (indicateur ou source officielle sur la ligne précédente). Contribue probablement au faible taux de rattachement (20 %) et à la part d'indéterminés. Il n'est pas établi que le corpus final contenait ces retours à la ligne : à vérifier sur le CSV d'origine.
**Correctif proposé** : remplacer les retours à la ligne simples par des espaces avant le découpage (conserver les doubles, qui séparent les paragraphes).

### L3 — Marqueurs cherchés comme sous-chaînes (modules 1.5, 2, 4) · `xfail`
Les listes de marqueurs sont testées avec `marqueur in phrase`. Conséquences : « demandeurs » déclenche le marqueur de prévision « demande » ; « par rapport à » déclenche l'acteur politique « rapport » ; « révise » contient « vise ». À l'inverse, les formes conjuguées ne sont pas reconnues : « atteindra » n'est pas une prévision (seul « atteindre » l'est).
**Effet** : bruit dans les deux sens sur la classification ; « par rapport à », très fréquent dans la presse économique, pousse vers le régime 2.
**Correctif proposé** : recherche en mot entier et listes de formes fléchies.

### L4 — « mai » trouvé dans « semaine » (module 2) · `xfail`
Les mois sont cherchés comme sous-chaînes : « semaine », « demain », « humain », « domaine » contiennent « mai ». Le chiffre reçoit alors la période `AAAA-05`.
**Effet** : fausses périodes mensuelles, donc gonflement possible du nombre de claims « à période infra-annuelle » (le ≈ 42) et comparaisons à un mauvais mois.
**Correctif proposé** : `re.search(rf"\b{mois}\b", phrase)`.

### L5 — « la hausse des prix » marquée comme variation (module 2) · `xfail`
« hausse » figure dans les marqueurs de variation, or « la hausse des prix » est la définition même de l'inflation. Un niveau d'inflation est alors traité comme une variation et exclu du fact-check.
**Effet** : compte des variations (575) surestimé ; claims d'inflation perdus pour le verdict. Sans effet sur la classification en régimes.

### L6 — IPCH annoncé, IPC interrogé (module 3)
Si la phrase mentionne « harmonisé » ou « IPCH », `CorrespondanceIdbank.resoudre` remplace le libellé par celui de l'IPCH mais conserve l'idBank de l'IPC (aucune série IPCH n'est déclarée). En 2023, l'IPCH était sensiblement supérieur à l'IPC : la comparaison serait faussée.
**Correctif proposé** : déclarer l'idBank de l'IPCH, ou marquer le cas comme non disponible.

### L7 — Taux d'une sous-population comparé au taux global (modules 1.5, 3)
« Le taux de chômage des jeunes grimpe à 17,6 % » contient le marqueur « taux de chômage » et passe en régime 1 sur l'indicateur chômage, alors que la série de référence est le taux global. Le filtre de plausibilité (2 à 15 %) écarte ce cas précis, pas un taux régional à 9 %.

### L8 — Découpage des événements (module `evenements.py`)
Fenêtre hebdomadaire ISO : un article du dimanche et sa reprise du lundi tombent dans deux événements. L'indicateur dominant dépend du lexique large du module 2 (« emploi », « croissance », « revenu », « immigr »), ce que le mémoire signale pour la « population ». Ces définitions ont été reconstruites d'après le texte : le découpage exact qui a donné 27 événements n'est pas connu.

### L9 — Ce que mesure l'indice de divergence (module 5)
Trois propriétés de la mesure limitent son interprétation comme « choix éditorial » :
1. **Unité = l'article, pas le média.** Deux articles du même média qui citent des chiffres différents comptent comme deux sélections divergentes.
2. **Univers = tous les chiffres de chaque article**, y compris ceux sans rapport avec l'événement. Des articles de longueur et d'angle différents partagent mécaniquement peu de chiffres.
3. **Pas de niveau de référence.** On ne sait pas quelle divergence produiraient des articles tirés au hasard la même semaine, ou deux articles d'un même média.

**Effet** : 0,80 mélange choix éditorial et hétérogénéité des articles ; il surestime probablement la part attribuable au premier.
**Pour aller plus loin** : agréger les chiffres par média avant le calcul, restreindre l'univers aux chiffres portant sur l'indicateur de l'événement, et comparer à une distribution obtenue par permutation des articles entre événements.

---

## C. Divergences entre le guide de codage (Annexe 3) et le code

Le guide de l'Annexe 3 décrit le jugement humain attendu ; il n'est pas une spécification du classifieur. Deux de ses neuf exemples sont classés différemment par le code (testé dans `tests/test_module1_5_classifieur.py`) :

| | Exemple | Guide | Code | Raison |
|---|---|---|---|---|
| D1 | « Un rapport chiffre à environ 15 milliards d'euros le coût pour les finances publiques. » | indéterminé | régime 2 | règle 4 : grandeur budgétaire sans indicateur officiel |
| D2 | « Le déficit public a représenté 5,5 % du PIB en 2023. » | indéterminé | régime 1 | l'exclusion « % du PIB » retire le PIB, pas le déficit |

Pour D2, le code est cohérent avec les chiffres du mémoire : les 24 claims « déficit » du régime 1 sont exactement ceux qui manquent entre 316 claims et 292 idBank résolus, le déficit en % du PIB n'ayant pas de série dans la BDM. Ces deux cas abaisseront mécaniquement l'accord lors de la validation.
