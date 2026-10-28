# Historique des versions

Le format s'inspire de [Keep a Changelog](https://keepachangelog.com/fr/1.1.0/). Les numéros suivent le [versionnage sémantique](https://semver.org/lang/fr/).

## [2.0.1] — 2026-10-28 — documentation alignée sur la soutenance

Aucune modification du code : les résultats et le comportement sont ceux de la 2.0.0.

### Modifié

- Licence : texte MIT standard, reconnu par GitHub. La mention « tous droits réservés » du mémoire passe dans `docs/memoire/README.md`.
- README : reformulation opérationnelle de la problématique ; paragraphe sur l'ordre d'exécution des modules (le mémoire et le diaporama présentent 1.5 avant 2, le code exécute 2 avant 1.5).
- `docs/memoire/` : mémoire remplacé par la version soutenue (corrections typographiques uniquement) ; diaporama de soutenance ajouté.
- `CITATION.cff` : version 2.0.1.

## [2.0.0] — 2026-10-16 — version du mémoire, reconstruite

Version correspondant aux règles décrites dans le mémoire déposé le 15 juillet 2026 (Partie II, §2.2 à §2.6).

**Important.** Le code de cette version n'avait pas été conservé : seule la v1 subsistait. Les changements ci-dessous ont été réécrits en octobre 2026 à partir du texte du mémoire et de ses annexes. Les règles correspondent au texte ; l'identité des résultats (6 399 claims, 316 en régime 1, 27 événements, divergence 0,80) n'a pas pu être revérifiée, le corpus n'étant pas accessible au moment de la publication. Voir [`docs/reproduire_les_resultats.md`](docs/reproduire_les_resultats.md).

### Reconstruit d'après le mémoire

- **Module 1.5** (§2.4.1)
  - Condition nécessaire : aucun claim en régime 1 sans indicateur officiel identifié dans la phrase. En v1, un « % » accompagné d'un verbe de constat suffisait, ce qui surévaluait le régime 1 (plus de 3 700 claims sur le corpus).
  - Trois exclusions : pays étranger sans marqueur français, année postérieure à la date de l'article, ratio « % du PIB » confondu avec la croissance.
  - Nouveau paramètre `date_article`.
- **Module 0** (§2.2.2)
  - Troncature du corps à la première mention de copyright Europresse (sur-extraction des cahiers spéciaux, jusqu'à 718 % du nombre de mots attendu, 13 articles concernés).
  - Normalisation du nom de média (11 articles portaient un intitulé de rubrique) ; valeur brute conservée dans `source_media_brut`.
- **Outil de corpus** (§2.2.2) : en cas de doublon, conservation de la version dont le taux d'extraction est le plus proche de 1.
- **Événements** (§2.6) : nouveau module `evenements.py` (indicateur dominant × semaine ISO, au moins 3 médias distincts). Remplace le rattachement de la v1 à 16 dates INSEE codées en dur.
- **Module 5** (Annexe 2) : codebook Entman aligné sur l'annexe du mémoire, recherche en mot entier.

### Ajouté

- `analyse_corpus.py` : exécution sur tout un corpus, agrégats de la Partie II dans l'ordre du mémoire, comparaison aux valeurs publiées (`--comparer-memoire`), options de sensibilité (`--min-medias`, `--chiffres`), vérification INSEE facultative (`--verifier-insee`).
- `corpus_io.py` : lecture d'un corpus CSV avec détection du séparateur.
- Interface en ligne de commande pour `pipeline_complet.py`.
- Corpus fictif d'exemple (`data/exemple/`).
- 90 tests pytest sans réseau, dont 5 limites connues écrites en `xfail` strict et un parcours complet du module 0 sur un PDF fictif à la mise en page Europresse ; intégration continue GitHub Actions (Python 3.10 à 3.13).
- Documentation : `README.md`, `docs/`, `data/README.md`, `CITATION.cff`, licence MIT.

### Corrigé

- **Module 3** : le mode mock lisait et écrivait le même cache SQLite que le mode production ; une valeur simulée pouvait ressortir plus tard étiquetée « INSEE-BDM (cache) ». Le mock n'utilise plus le cache. Sans effet sur les chiffres du mémoire (aucun verdict n'y est publié).

### Modifié

- `test_m3_reel.py` renommé `verifier_api_insee.py` : ce script interroge l'API réelle, ce n'est pas un test automatique.
- Démo du module 5 : médias fictifs à la place de titres de presse réels.

### Conservé volontairement

Les défauts repérés dans les modules 1 et 2 (limites L1 à L5) n'ont **pas** été corrigés, pour que le code reste celui qui a produit les résultats du mémoire. Ils sont décrits, avec leur effet probable et un correctif proposé, dans [`docs/limites_connues.md`](docs/limites_connues.md).

## [1.0.0] — 2026-06-22 — état conservé dans le projet

Instantané non modifié des dix scripts du pipeline au 22 juin 2026 (modules 0 à 5, orchestrateur, outil de statistiques, test de l'API INSEE). Classifieur de régimes v1 : 6 526 claims dont 67 % en régime 1 sur le corpus, 14 événements rattachés à une grille de dates INSEE. Conservé pour que l'écart avec la version du mémoire reste lisible (`git diff v1.0.0 v2.0.0`).
