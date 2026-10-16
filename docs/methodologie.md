# Choix méthodologiques

Ce document résume les décisions qui structurent le code et renvoie au mémoire ([`memoire/`](memoire/)) pour l'argumentation complète.

## 1. Ce que le pipeline détecte, et ce qu'il ne détecte pas

La typologie de Wardle et Derakhshan (2017) distingue la mésinformation (erreur sans intention), la désinformation (fausseté intentionnelle) et la malinformation (élément exact utilisé pour nuire). L'intention n'est pas observable dans un texte. Le pipeline mesure donc deux choses plus étroites :

- des **écarts** entre un chiffre cité et la statistique officielle correspondante (régime 1) ;
- des **différences de sélection** des chiffres entre médias couvrant un même événement (régime 2).

Un verdict « incorrect » signale un écart factuel, pas une volonté de tromper. Une divergence de sélection signale un cadrage différent, pas une fausseté.

## 2. Deux régimes de vérifiabilité (§2.1.1)

La question « ce chiffre est-il vrai ? » n'a de sens que si une mesure officielle unique lui correspond. D'où la séparation :

- **Régime 1** : indicateur officiel identifié, valeur constatée, période passée. Vérifiable.
- **Régime 2** : objectif, prévision, estimation, ratio construit, chiffre étranger. Non vérifiable par confrontation ; seul son cadrage s'analyse.
- **Indéterminé** : indices absents ou contradictoires. Le pipeline ne force pas la décision.

Hypothèses de travail : H1, le régime 1 est minoritaire ; H2, la sélection des chiffres de régime 2 diverge fortement entre médias pour un même événement.

## 3. Interprétabilité plutôt qu'apprentissage (§2.1.2)

Toutes les décisions reposent sur des règles explicites (expressions régulières, lexiques, scores additifs). Chaque claim sort avec la justification de son classement. Ce choix sacrifie de la couverture au profit de la traçabilité : un verdict de fact-checking doit pouvoir être expliqué au lecteur. Contrepartie : les règles lexicales ont des angles morts identifiables ([`limites_connues.md`](limites_connues.md)).

## 4. Seuils de tolérance justifiés (module 4)

Des seuils fixes (2 %, 8 %, 20 % d'écart relatif) seraient arbitraires. Le seuil « confirmé » est ancré dans deux grandeurs mesurables :

1. **L'arrondi du journaliste** : écrire « 4,3 % » pour 4,28 % n'est pas une erreur. La tolérance vaut la demi-unité du dernier chiffre écrit (0,05 pour une décimale).
2. **L'incertitude de la statistique** : un écart inférieur à la marge d'erreur de la mesure INSEE ne peut pas être qualifié d'erreur factuelle.

Le seuil retenu est le plus grand des deux ; les verdicts dégradés sont des multiples de ce seuil (2,5 et 5). Les marges INSEE restent à confirmer indicateur par indicateur (limite V3).

## 5. Une série de référence par indicateur (module 3)

Le mot « chômage » peut désigner le taux BIT de l'INSEE ou les inscrits à France Travail ; « inflation », l'IPC ou l'IPCH. Le pipeline retient une série par indicateur, justifiée dans [`idbank_insee.md`](idbank_insee.md), et refuse explicitement les comparaisons hors périmètre.

## 6. Cadrage sans profil éditorial a priori (module 5)

Une première version du module 5 attribuait à chaque titre un profil éditorial (orientation, vocabulaire typique) : le résultat aurait reflété ces hypothèses plutôt que les données. Ces profils ont été retirés. La mesure principale est **inductive** : sur l'ensemble des chiffres d'un événement, lesquels chaque article cite ou omet. Les marqueurs d'Entman (1993) ne sont qu'un éclairage secondaire, interprétatif, documenté dans l'Annexe 2 et destiné à une validation par double codage.

## 7. Validation prévue (§2.4.2, Annexe 3)

Échantillon aléatoire d'environ 100 claims, au moins deux codeurs, codage en aveugle de la décision du classifieur, pourcentage d'accord et κ de Cohen interprété avec les seuils de Landis et Koch (1977). Non exécuté dans le cadre du mémoire : tant qu'il ne l'est pas, l'ordre de grandeur d'un régime 1 minoritaire est tenu pour robuste et le chiffre exact pour provisoire.

## Références citées

- Entman, R. M. (1993). Framing: Toward clarification of a fractured paradigm. *Journal of Communication*, 43(4), 51-58. https://doi.org/10.1111/j.1460-2466.1993.tb01304.x
- Landis, J. R., & Koch, G. G. (1977). The measurement of observer agreement for categorical data. *Biometrics*, 33(1), 159-174. https://doi.org/10.2307/2529310
- Wardle, C., & Derakhshan, H. (2017). *Information disorder: Toward an interdisciplinary framework for research and policymaking* (Report DGI(2017)09). Council of Europe.

La bibliographie complète figure dans le mémoire.
