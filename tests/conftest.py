"""Configuration commune des tests.

Les modules du pipeline s'importent entre eux par leur nom de fichier
(`from module1_extraction import ...`) : on ajoute donc le dossier
`pipeline/` au chemin d'import, comme lorsqu'on lance un script avec
`python pipeline/xxx.py`.
"""

import logging
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE / "pipeline"))

CORPUS_EXEMPLE = RACINE / "data" / "exemple" / "corpus_exemple.csv"

# Les modules configurent un logging INFO verbeux à l'import.
logging.disable(logging.INFO)
