# -*- coding: utf-8 -*-
"""
Tests de src.utils.git_sync sur de vrais depots git temporaires.

On simule le poste metier : un depot "origin" nu, un clone "poste", et un
second clone "dev" qui pousse un nouveau commit. Chaque test reproduit un des
cas rencontres en production (fichier non suivi, fichier suivi modifie,
collision) et verifie le statut, le marqueur et le HEAD final.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from src.utils.git_sync import (
    STATUT_A_JOUR,
    STATUT_BLOQUE,
    STATUT_ECHEC,
    STATUT_MIS_A_JOUR,
    chemin_marqueur,
    chemin_verrou,
    fichiers_suivis_modifies,
    synchroniser,
)

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git absent du PATH")

# Identite jetable, et hooks neutralises : un core.hooksPath global (garde-fou
# anti-secrets du poste) s'appliquerait sinon aux depots de test et ferait
# echouer leurs commits pour une raison etrangere au code teste. Le chemin
# pointe un dossier inexistant, git n'y trouve donc aucun hook.
IDENTITE = [
    "-c", "user.name=Test", "-c", "user.email=test@example.com",
    "-c", "commit.gpgsign=false",
    "-c", f"core.hooksPath={Path(tempfile.gettempdir()) / 'fuseau_test_sans_hook'}",
]


def _git(cwd: Path, *args: str) -> str:
    res = subprocess.run(["git", *IDENTITE, *args], cwd=cwd, capture_output=True, text=True)
    assert res.returncode == 0, f"git {' '.join(args)} : {res.stderr or res.stdout}"
    return res.stdout.strip()


def _commit(depot: Path, chemin: str, contenu: str, message: str) -> None:
    fichier = depot / chemin
    fichier.parent.mkdir(parents=True, exist_ok=True)
    fichier.write_text(contenu, encoding="utf-8")
    _git(depot, "add", chemin)
    _git(depot, "commit", "-q", "-m", message)


@pytest.fixture()
def depots(tmp_path: Path) -> tuple[Path, Path]:
    """Retourne (poste, dev), deux clones d'un meme origin, synchronises sur main."""
    origin = tmp_path / "origin.git"
    _git(tmp_path, "init", "-q", "--bare", "-b", "main", str(origin))
    dev = tmp_path / "dev"
    _git(tmp_path, "clone", "-q", str(origin), str(dev))
    _git(dev, "checkout", "-q", "-b", "main")
    _commit(dev, "app.py", "v1\n", "init")
    _git(dev, "push", "-q", "origin", "main")
    poste = tmp_path / "poste"
    _git(tmp_path, "clone", "-q", "-b", "main", str(origin), str(poste))
    return poste, dev


def _pousser_evolution(dev: Path, chemin: str = "app.py", contenu: str = "v2\n") -> None:
    _commit(dev, chemin, contenu, "evolution")
    _git(dev, "push", "-q", "origin", "main")


def test_fichiers_suivis_modifies_ignore_non_suivis() -> None:
    sortie = " M app.py\n?? rapport.docx\nM  config/x.yaml\nR  a.py -> b.py\n"
    assert fichiers_suivis_modifies(sortie) == ["app.py", "config/x.yaml", "a.py -> b.py"]


def test_fichier_non_suivi_ne_bloque_plus(depots: tuple[Path, Path]) -> None:
    """Cas du .docx du 22/09 : avant, le pull etait annule pendant deux jours."""
    poste, dev = depots
    (poste / "rapport.docx").write_bytes(b"binaire")
    (poste / "erreur.log.err").write_text("trace", encoding="utf-8")
    _pousser_evolution(dev)

    resultat = synchroniser(poste, "main")

    assert resultat.statut == STATUT_MIS_A_JOUR
    assert resultat.retard == 1
    assert resultat.head_apres != resultat.head_avant
    assert (poste / "app.py").read_text(encoding="utf-8") == "v2\n"
    assert not chemin_marqueur(poste).exists()


def test_fichier_suivi_modifie_bloque_et_ecrit_marqueur(depots: tuple[Path, Path]) -> None:
    poste, dev = depots
    (poste / "app.py").write_text("bricolage local\n", encoding="utf-8")
    _pousser_evolution(dev)

    resultat = synchroniser(poste, "main")

    assert resultat.statut == STATUT_BLOQUE
    assert not resultat.ok
    assert resultat.fichiers == ["app.py"]
    assert resultat.head_apres == resultat.head_avant
    contenu = chemin_marqueur(poste).read_text(encoding="utf-8")
    assert "app.py" in contenu
    assert resultat.head_avant in contenu
    assert resultat.distant is not None and resultat.distant in contenu


def test_collision_non_suivi_est_un_echec_signale(depots: tuple[Path, Path]) -> None:
    """Un non suivi qui porte le chemin d'un fichier ajoute en distant fait refuser le merge."""
    poste, dev = depots
    (poste / "nouveau.py").write_text("copie locale\n", encoding="utf-8")
    _pousser_evolution(dev, "nouveau.py", "version distante\n")

    resultat = synchroniser(poste, "main")

    assert resultat.statut == STATUT_ECHEC
    assert "merge" in resultat.message
    assert chemin_marqueur(poste).exists()
    assert (poste / "nouveau.py").read_text(encoding="utf-8") == "copie locale\n"


def test_pull_reussi_supprime_le_marqueur(depots: tuple[Path, Path]) -> None:
    poste, dev = depots
    (poste / "app.py").write_text("bricolage local\n", encoding="utf-8")
    _pousser_evolution(dev)
    assert synchroniser(poste, "main").statut == STATUT_BLOQUE
    assert chemin_marqueur(poste).exists()

    _git(poste, "restore", "app.py")
    resultat = synchroniser(poste, "main")

    assert resultat.statut == STATUT_MIS_A_JOUR
    assert not chemin_marqueur(poste).exists()


def test_deja_a_jour(depots: tuple[Path, Path]) -> None:
    poste, _ = depots
    resultat = synchroniser(poste, "main")
    assert resultat.statut == STATUT_A_JOUR
    assert resultat.retard == 0
    assert resultat.ok


def test_fetch_impossible_est_un_echec(tmp_path: Path) -> None:
    poste = tmp_path / "seul"
    poste.mkdir()
    _git(poste, "init", "-q", "-b", "main")
    _commit(poste, "app.py", "v1\n", "init")

    resultat = synchroniser(poste, "main")

    assert resultat.statut == STATUT_ECHEC
    assert "fetch" in resultat.message
    assert chemin_marqueur(poste).exists()


def test_pulls_concurrents_finissent_tous_sur_le_distant(depots: tuple[Path, Path]) -> None:
    """
    Cas du 08/10 : Files_ETL et Daily_ETL tirent a la meme seconde. Le verrou
    les serialise, le second constate qu'il est deja a jour, et aucun des deux
    n'annonce un succes sans que HEAD ait rejoint le distant.
    """
    poste, dev = depots
    _pousser_evolution(dev)
    attendu = _git(dev, "rev-parse", "HEAD")

    with ThreadPoolExecutor(max_workers=3) as pool:
        resultats = list(pool.map(lambda o: synchroniser(poste, "main", origine=o), ["a", "b", "c"]))

    assert all(r.ok for r in resultats)
    assert sorted(r.statut for r in resultats) == [STATUT_A_JOUR, STATUT_A_JOUR, STATUT_MIS_A_JOUR]
    assert _git(poste, "rev-parse", "HEAD") == attendu
    assert not chemin_verrou(poste).exists()


def test_fetch_head_reecrit_ne_trompe_plus_le_pull(depots: tuple[Path, Path]) -> None:
    """Un fetch tiers qui reecrit FETCH_HEAD vers l'ancien commit ne change plus la cible."""
    poste, dev = depots
    ancien = _git(poste, "rev-parse", "HEAD")
    _pousser_evolution(dev)
    (poste / ".git" / "FETCH_HEAD").write_text(f"{ancien}\t\tbranch 'main' of x\n", encoding="utf-8")

    resultat = synchroniser(poste, "main")

    assert resultat.statut == STATUT_MIS_A_JOUR
    assert _git(poste, "rev-parse", "HEAD") == _git(dev, "rev-parse", "HEAD")


def test_verrou_tenu_est_un_echec_signale(depots: tuple[Path, Path]) -> None:
    poste, dev = depots
    _pousser_evolution(dev)
    verrou = chemin_verrou(poste)
    verrou.parent.mkdir(parents=True, exist_ok=True)
    verrou.write_text("pid=autre", encoding="utf-8")

    resultat = synchroniser(poste, "main", attente_verrou_s=0.5)

    assert resultat.statut == STATUT_ECHEC
    assert "verrou" in resultat.message
    assert chemin_marqueur(poste).exists()
    assert verrou.exists(), "le verrou d'un autre processus ne doit pas etre supprime"


def test_verrou_perime_est_repris(depots: tuple[Path, Path]) -> None:
    poste, dev = depots
    _pousser_evolution(dev)
    verrou = chemin_verrou(poste)
    verrou.parent.mkdir(parents=True, exist_ok=True)
    verrou.write_text("pid=mort", encoding="utf-8")
    vieux = time.time() - 3600
    os.utime(verrou, (vieux, vieux))

    resultat = synchroniser(poste, "main", attente_verrou_s=0.5)

    assert resultat.statut == STATUT_MIS_A_JOUR
    assert not verrou.exists()


def test_cible_tag(depots: tuple[Path, Path]) -> None:
    """BRANCHE_DEPLOIEMENT peut pointer un tag de release (annote ici)."""
    poste, dev = depots
    _pousser_evolution(dev)
    _git(dev, "tag", "-a", "v1", "-m", "release")
    _git(dev, "push", "-q", "origin", "v1")
    _pousser_evolution(dev, contenu="v3 non publiee\n")

    resultat = synchroniser(poste, "v1")

    assert resultat.statut == STATUT_MIS_A_JOUR
    assert (poste / "app.py").read_text(encoding="utf-8") == "v2\n"
