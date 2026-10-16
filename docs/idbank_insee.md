# Séries INSEE de référence (idBank)

Le module 3 confronte chaque chiffre de régime 1 à **une** série de la Banque de données macroéconomiques (BDM) de l'INSEE. Le choix de cette série est une décision méthodologique : un même mot de presse peut renvoyer à plusieurs séries.

## Séries retenues

Identifiées en mai-juin 2026 à partir du fichier officiel `correspondance_idbank_dimension.csv` (version 202603), dimensions contrôlées une à une, puis interrogées avec succès en conditions réelles (4 séries sur 4).

| Indicateur | idBank | Série | Fréquence |
|---|---|---|---|
| Inflation | `011814632` | IPC, ensemble des ménages, France, glissement annuel (%) | mensuelle |
| Chômage | `001688527` | Taux de chômage au sens du BIT, France hors Mayotte, 15 ans ou plus, CVS (%) | trimestrielle |
| PIB | `011794844` | Taux de croissance trimestriel du PIB en volume, CVS-CJO (%) | trimestrielle |
| Dette | `010777608` | Dette publique au sens de Maastricht, administrations publiques (% du PIB) | trimestrielle |
| Déficit (% du PIB) | — | **Pas de série dans la BDM** | — |

Alternatives déclarées dans `CorrespondanceIdbank.TABLE` : France métropolitaine pour l'inflation (`011814614`) et le chômage (`001688526`) ; besoin de financement des APU en euros courants pour le déficit (`001718848`).

## Décisions et justifications

- **Champ géographique** : France entière ou hors Mayotte, champ de communication de l'INSEE, plutôt que la métropole. Un article qui cite le chiffre métropolitain peut donc recevoir un écart qui n'est pas une erreur.
- **Chômage** : taux au sens du BIT (INSEE), à ne pas confondre avec les demandeurs d'emploi inscrits à France Travail. Le module 3 refuse la comparaison quand la phrase cite France Travail, Pôle emploi ou la catégorie A.
- **Déficit** : le ratio « 5,5 % du PIB » est publié dans les communiqués mais n'est pas servi comme série. Ces claims restent en régime 1 (ce sont des constats officiels) mais ne sont pas vérifiables automatiquement : ils expliquent l'écart entre 316 claims de régime 1 et 292 idBank résolus.
- **Révisions** : l'API renvoie la valeur actuelle, pas celle publiée à la date de l'article. Le paramètre `includeHistory=true` (option `inclure_revisions`) récupère l'historique, mais le pipeline ne sélectionne pas automatiquement la version en vigueur à la date de l'article.

## Accès à l'API

```text
https://www.bdm.insee.fr/series/sdmx/data/SERIES_BDM/{idbank}?startPeriod=2023-Q3&endPeriod=2023-Q3
```

- Service web SDMX 2.1, gratuit, sans compte ni clé, jusqu'à 400 idBank par requête (séparés par `+`).
- Réponse XML au format *StructureSpecific* : période et valeur sont des attributs de `<Obs>` (`TIME_PERIOD`, `OBS_VALUE`, `OBS_QUAL`).
- Service toujours en ligne en octobre 2026 ; page de documentation INSEE mise à jour le 30/06/2026 : <https://www.insee.fr/fr/information/2868055>.

## Vérifier les séries avant un nouveau calcul

Les idBank peuvent changer (changement d'année de base, arrêt d'une série). Avant toute exécution en production :

```bash
python pipeline/verifier_api_insee.py
```

Le script interroge les quatre séries et compare les valeurs à des premières publications connues. Un écart signalé par ⚠️ peut venir d'une révision INSEE et non d'une erreur du module. En cas d'échec, vérifier la série sur `https://www.insee.fr/fr/statistiques/serie/{idbank}` ou dans le fichier de correspondance publié par l'INSEE, puis mettre à jour `CorrespondanceIdbank.TABLE`.

Les valeurs « mock » du module 3 (mode sans réseau) ont été saisies à la main pour les démonstrations et les tests : elles ne constituent pas une vérité terrain.
