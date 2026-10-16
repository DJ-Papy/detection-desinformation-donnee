#!/usr/bin/env python3
"""
TEST M3 EN CONDITIONS RÉELLES — à lancer sur TA machine (accès Internet)
========================================================================

Ce script teste le client API INSEE sur les 4 séries vérifiées, en
interrogeant réellement bdm.insee.fr. Il vérifie aussi la cohérence des
valeurs renvoyées.

PRÉREQUIS
  - Être sur une machine avec accès Internet (PAS derrière un proxy bloquant)
  - Avoir le fichier module3_matching_insee.py dans le même dossier

UTILISATION
  python test_m3_reel.py

Le script affiche, pour chaque série :
  - la valeur récupérée pour une période connue
  - si elle correspond à la valeur attendue (test de cohérence)
  - le XML brut en cas de problème (pour me l'envoyer si ça coince)

EN CAS DE PROBLÈME
  Si une série échoue, le script affiche l'URL et l'erreur. Copie-moi le
  message : je corrige. Les causes possibles : format de période, en-tête
  HTTP, ou structure XML légèrement différente selon les séries.
"""

import sys
import urllib.request
import urllib.error

# Import du module (doit être dans le même dossier)
try:
    from module3_matching_insee import Module3MatchingINSEE, ClientBDM
except ImportError:
    print("❌ Place ce script dans le même dossier que module3_matching_insee.py")
    sys.exit(1)


# Séries à tester : (indicateur, période, valeur attendue approx, tolérance)
# Valeurs attendues = valeurs publiées connues (à ajuster si besoin)
TESTS = [
    ("chômage",   "2023-Q4", 7.5,   0.3,  "Chômage T4 2023 (France hors Mayotte)"),
    ("inflation", "2023-07", 4.3,   0.3,  "Inflation juillet 2023"),
    ("PIB",       "2024-Q2", 0.2,   0.3,  "PIB T2 2024 (variation volume)"),
    ("dette",     "2023-Q2", 111.8, 1.0,  "Dette publique T2 2023 (% PIB)"),
]


def test_url_directe(idbank):
    """Teste l'accès brut à une série, retourne (ok, contenu_ou_erreur)."""
    url = f"https://www.bdm.insee.fr/series/sdmx/data/SERIES_BDM/{idbank}?lastNObservations=2"
    try:
        req = urllib.request.Request(url, headers={"Accept": "application/xml"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            return True, resp.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        return False, f"HTTP {e.code} : {e.reason}\nURL : {url}"
    except Exception as e:
        return False, f"{type(e).__name__} : {e}\nURL : {url}"


def main():
    print("=" * 68)
    print("TEST M3 EN CONDITIONS RÉELLES — API INSEE BDM")
    print("=" * 68)

    # Étape 0 : test de connectivité brute sur une série
    print("\n[0] Test de connectivité brute (chômage)...")
    ok, contenu = test_url_directe("001688527")
    if not ok:
        print(f"❌ Échec de connexion : {contenu}")
        print("\n→ Vérifie ta connexion / proxy. Si l'erreur persiste, copie-la moi.")
        return
    print("✅ Connexion OK, l'API répond.")
    print(f"   Aperçu du XML reçu (200 premiers caractères) :")
    print("   " + contenu[:200].replace("\n", " "))

    # Étape 1 : test via le module M3 sur les 4 séries
    print("\n[1] Test des 4 séries via le module M3 (mode production)\n")
    m3 = Module3MatchingINSEE(mode="production")

    succes, total = 0, 0
    for indic, periode, attendu, tol, libelle in TESTS:
        total += 1
        d = m3.matcher("TEST", indic, periode,
                       phrase=f"valeur officielle {indic} {periode}")
        if d.trouve and d.valeur is not None:
            ecart = abs(d.valeur - attendu)
            coherent = ecart <= tol
            sym = "✅" if coherent else "⚠️"
            print(f"{sym} {libelle}")
            print(f"     valeur INSEE = {d.valeur}{d.unite} "
                  f"(attendu ≈ {attendu}, écart {ecart:.2f})")
            print(f"     série : {d.libelle}")
            if d.note:
                print(f"     note  : {d.note}")
            if coherent:
                succes += 1
            else:
                print(f"     ⚠️ Écart > tolérance : période ou série à vérifier")
        else:
            print(f"❌ {libelle}")
            print(f"     ÉCHEC : {d.note}")
            print(f"     idbank tenté : {d.idbank}")
        print()

    m3.fermer()

    print("=" * 68)
    print(f"RÉSULTAT : {succes}/{total} séries cohérentes")
    if succes == total:
        print("🎉 M3 est pleinement opérationnel en conditions réelles !")
    else:
        print("Certaines séries posent problème. Causes possibles :")
        print("  - format de période (mensuel 2023-07 vs trimestriel 2023-Q4)")
        print("  - valeur attendue à ajuster (révisions INSEE)")
        print("  → Copie-moi la sortie complète, j'ajuste le module.")
    print("=" * 68)


if __name__ == "__main__":
    main()
