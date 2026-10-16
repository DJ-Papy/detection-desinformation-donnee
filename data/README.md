# Données

## Ce que contient ce dossier

| Chemin | Contenu | Versionné ? |
|---|---|---|
| `exemple/corpus_exemple.csv` | 10 articles **fictifs** pour faire tourner le pipeline et les tests | oui |
| `corpus/` | votre propre corpus (PDF Europresse, CSV dérivés) | **non** (`.gitignore`) |

## Pourquoi le corpus du mémoire n'est pas publié

Le mémoire repose sur 562 articles du *Monde*, des *Échos*, du *Figaro*, de *Libération*, de *L'Obs*, du *Point* et de l'AFP, collectés manuellement sur Europresse en 2026. Ces textes appartiennent à leurs éditeurs : les republier, même partiellement, n'est pas permis. Les contrats d'accès Europresse des bibliothèques universitaires interdisent en outre, en général, la fouille de textes et le téléchargement massif ; vérifiez les conditions propres à votre établissement avant toute collecte.

Ce qui peut être partagé sans les textes : la liste des identifiants Europresse des articles (champ `news·AAAAMMJJ·SOURCE·…`), qui permet à une personne disposant d'un accès de reconstituer le même corpus. Elle n'est pas incluse à ce jour.

## Format attendu par le pipeline

Un fichier CSV encodé en UTF-8, une ligne par article, avec au minimum ces colonnes :

| Colonne | Contenu | Exemple |
|---|---|---|
| `id` | identifiant unique | `news·20231115·AFPD·xyz` ou `EX-0001` |
| `media` | nom du média, normalisé | `Le Monde` |
| `date` | date de publication, AAAA-MM-JJ | `2023-11-15` |
| `titre` | titre de l'article | |
| `texte` | corps de l'article | |

- Séparateur `;`, `|`, `,` ou tabulation : il est détecté automatiquement sur la ligne d'en-tête.
- Les textes peuvent contenir des retours à la ligne s'ils sont entre guillemets. **Attention** : le module 1 traite chaque retour à la ligne comme une fin de phrase (limite L2). Si votre source coupe les phrases en lignes de colonnes, recollez les lignes d'un même paragraphe avant l'analyse.
- Les colonnes supplémentaires sont conservées et ignorées.
- Un identifiant répété n'est lu qu'une fois.

`pipeline/outil_corpus_stats.py` produit ce format à partir d'un dossier d'exports PDF Europresse.

## Le corpus d'exemple

Les médias (*Quotidien Alpha*, *Quotidien Bêta*, *Journal Gamma*, *Hebdo Delta*, *Agence Epsilon*), les titres et les textes sont inventés. Les chiffres reprennent des ordres de grandeur réels de 2023-2024 pour que la démonstration ait du sens, sans prétendre reproduire un article existant.

Il a été écrit pour exercer chaque branche du pipeline :

| Article | Ce qu'il illustre |
|---|---|
| EX-0001 à EX-0004 | un événement « chômage, semaine 46 de 2023 » couvert par 4 médias ; trois chiffres confirmés, un approximatif |
| EX-0005 à EX-0007 | un événement « inflation, semaine 30 de 2023 » ; chiffre étranger exclu (zone euro), pourcentage sans indicateur classé indéterminé |
| EX-0008 | ratio « 110,6 % du PIB » rattaché à la dette et non à la croissance ; chiffres suivis d'une année perdus à l'extraction (limite L1) |
| EX-0009 | objectif chiffré daté (année future) et chiffre allemand, tous deux en régime 2 |
| EX-0010 | article sans affirmation chiffrée (type « agenda ») |
