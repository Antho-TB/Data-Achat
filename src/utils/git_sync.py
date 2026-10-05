# -*- coding: utf-8 -*-
"""
[UTIL]
=============================================================================
SYNCHRONISATION GIT DU POSTE METIER (auto-pull)
=============================================================================

Le poste de Marlene met son code a jour par un 'git pull' automatique. Trois
fois, ce pull a ete annule sans que personne ne s'en rende compte : un
'.log.err' le 28/07, une sauvegarde '.env' le 06/08, un '.docx' non suivi du
22 au 24/09. Dans le dernier cas, l'ETL a tourne deux jours sur l'ancien code.

La cause commune : la decision de bloquer reposait sur 'git status --porcelain',
qui liste aussi les fichiers NON SUIVIS. Or un fichier non suivi ne gene pas un
pull en avance rapide. Seuls les fichiers SUIVIS et modifies sont un vrai
risque, parce que git refuserait de les ecraser ou qu'on perdrait une
modification locale. D'ou '--untracked-files=no' pour la decision.

Le cas limite : un fichier non suivi qui porte le meme chemin qu'un fichier
ajoute par le commit distant. git refuse alors le merge ("untracked working
tree files would be overwritten"). Ce n'est pas detectable a l'avance a bas
cout, on le traite donc comme un echec du merge, signale comme tel.

Quand le pull n'aboutit pas, on ecrit un marqueur deploy/logs/PULL_BLOQUE.txt
(lisible sans ouvrir les journaux) et on le supprime au premier pull reussi.
Le meme comportement existe cote PowerShell dans
src/scripts/infrastructure/run_etl_scheduled.ps1, qui fait le pull quotidien.

Junior Tip : on fetch une seule fois puis on fusionne FETCH_HEAD. Comparer
HEAD a FETCH_HEAD donne le retard reel, y compris quand la cible est un tag
(un tag ne met pas a jour origin/<nom>).
"""
from __future__ import annotations

import logging
import subprocess
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

STATUT_A_JOUR = "a_jour"
STATUT_MIS_A_JOUR = "mis_a_jour"
STATUT_BLOQUE = "bloque"
STATUT_ECHEC = "echec"

NOM_MARQUEUR = "PULL_BLOQUE.txt"


@dataclass(frozen=True)
class ResultatSync:
    """Issue d'une tentative de synchronisation du depot local."""

    statut: str
    branche: str
    head_avant: str
    head_apres: str
    distant: str | None = None
    retard: int | None = None
    fichiers: list[str] = field(default_factory=list)
    message: str = ""

    @property
    def ok(self) -> bool:
        """Vrai si le code local est celui de la branche cible."""
        return self.statut in (STATUT_A_JOUR, STATUT_MIS_A_JOUR)


def chemin_marqueur(racine: Path) -> Path:
    """Emplacement du marqueur, dans deploy/logs (deja couvert par le .gitignore)."""
    return racine / "deploy" / "logs" / NOM_MARQUEUR


def fichiers_suivis_modifies(porcelain: str) -> list[str]:
    """
    Extrait les chemins d'une sortie 'git status --porcelain'.

    Format v1 : deux caracteres d'etat, un espace, puis le chemin. Un
    renommage s'ecrit 'R  ancien -> nouveau' : on garde la ligne entiere apres
    l'etat, l'operateur a besoin des deux noms pour comprendre. Les lignes
    '??' (non suivis) sont ecartees par securite, meme si l'appelant passe
    deja '--untracked-files=no'.
    """
    fichiers: list[str] = []
    for ligne in porcelain.splitlines():
        if len(ligne) < 4 or ligne.startswith("??") or ligne.startswith("!!"):
            continue
        fichiers.append(ligne[3:].strip())
    return fichiers


def _git(racine: Path, *args: str, timeout: int = 30) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(racine), *args],
        capture_output=True, text=True, timeout=timeout,
    )


def _sortie(res: subprocess.CompletedProcess[str]) -> str:
    return (res.stderr.strip() or res.stdout.strip()).replace("\n", " | ")


def _head_court(racine: Path, ref: str = "HEAD") -> str:
    try:
        res = _git(racine, "rev-parse", "--short", ref)
    except (OSError, subprocess.SubprocessError):
        return "inconnu"
    return res.stdout.strip() if res.returncode == 0 else "inconnu"


def ecrire_marqueur(racine: Path, resultat: ResultatSync) -> Path:
    """Ecrit le marqueur PULL_BLOQUE.txt, lisible par un non-developpeur."""
    marqueur = chemin_marqueur(racine)
    marqueur.parent.mkdir(parents=True, exist_ok=True)
    lignes = [
        "PULL AUTOMATIQUE BLOQUE : le poste ne tourne PAS sur le code de la branche cible.",
        f"Horodatage   : {datetime.now():%Y-%m-%d %H:%M:%S}",
        f"Statut       : {resultat.statut}",
        f"Branche      : {resultat.branche}",
        f"HEAD local   : {resultat.head_avant}",
        f"Distant      : {resultat.distant or 'inconnu'}",
        f"Retard       : {resultat.retard if resultat.retard is not None else 'inconnu'} commit(s)",
        f"Detail       : {resultat.message}",
        "Fichiers en cause :",
        *([f"  - {f}" for f in resultat.fichiers] or ["  (aucun, voir Detail)"]),
        "",
        "A faire : 'git status' a la racine du depot, ranger ou annuler les fichiers",
        "listes ('git restore <fichier>' si la modification est inutile), puis",
        f"'git pull origin {resultat.branche} --ff-only'. Ce fichier disparait au",
        "prochain pull reussi.",
    ]
    marqueur.write_text("\n".join(lignes) + "\n", encoding="utf-8")
    return marqueur


def synchroniser(racine: Path, branche: str) -> ResultatSync:
    """
    Met le depot a jour en avance rapide sur origin/<branche>.

    Ne leve jamais : l'appelant doit pouvoir continuer sur le code local. Le
    marqueur est ecrit ou supprime selon l'issue, et chaque etape est
    journalisee avec le sha court avant/apres.
    """
    head_avant = _head_court(racine)
    logger.info("[GIT] [INFO] HEAD local avant synchro : %s (cible %s)", head_avant, branche)

    def _conclure(resultat: ResultatSync) -> ResultatSync:
        if resultat.ok:
            chemin_marqueur(racine).unlink(missing_ok=True)
        else:
            marqueur = ecrire_marqueur(racine, resultat)
            logger.error("[GIT] [ECHEC] Pull bloque (%s) : %s. Marqueur : %s",
                         resultat.statut, resultat.message, marqueur)
            for fichier in resultat.fichiers:
                logger.error("[GIT] [ATTENTION]   fichier en cause : %s", fichier)
        return resultat

    try:
        fetch = _git(racine, "fetch", "origin", branche, timeout=60)
        if fetch.returncode != 0:
            return _conclure(ResultatSync(
                STATUT_ECHEC, branche, head_avant, head_avant,
                message=f"fetch impossible : {_sortie(fetch)}",
            ))

        distant = _head_court(racine, "FETCH_HEAD")
        compte = _git(racine, "rev-list", "--count", "HEAD..FETCH_HEAD")
        retard = int(compte.stdout.strip()) if compte.returncode == 0 else None
        logger.info("[GIT] [INFO] %s distant : %s, retard du poste : %s commit(s)",
                    branche, distant, retard if retard is not None else "inconnu")

        statut = _git(racine, "status", "--porcelain", "--untracked-files=no")
        fichiers = fichiers_suivis_modifies(statut.stdout)
        if fichiers:
            return _conclure(ResultatSync(
                STATUT_BLOQUE, branche, head_avant, head_avant, distant, retard, fichiers,
                message="fichiers suivis modifies localement, pull annule",
            ))

        if retard == 0:
            logger.info("[GIT] [SUCCES] Deja a jour sur %s (%s).", branche, head_avant)
            return _conclure(ResultatSync(
                STATUT_A_JOUR, branche, head_avant, head_avant, distant, retard,
            ))

        merge = _git(racine, "merge", "--ff-only", "FETCH_HEAD")
        if merge.returncode != 0:
            # Cas typique : un fichier non suivi collisionne avec un fichier
            # ajoute par le distant, ou des commits locaux divergent.
            return _conclure(ResultatSync(
                STATUT_ECHEC, branche, head_avant, head_avant, distant, retard,
                message=f"merge --ff-only refuse : {_sortie(merge)}",
            ))

        head_apres = _head_court(racine)
        logger.info("[GIT] [SUCCES] Code mis a jour : %s -> %s", head_avant, head_apres)
        return _conclure(ResultatSync(
            STATUT_MIS_A_JOUR, branche, head_avant, head_apres, distant, retard,
        ))
    except (OSError, subprocess.SubprocessError, ValueError) as exc:
        return _conclure(ResultatSync(
            STATUT_ECHEC, branche, head_avant, head_avant,
            message=f"synchronisation impossible : {exc}",
        ))
