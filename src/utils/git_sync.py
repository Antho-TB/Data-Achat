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

Le 08/10, le pull a annonce "[SUCCES] f43f1cd -> f43f1cd" en laissant 7
commits de cote. Les trois taches du poste partent a la meme seconde a
l'ouverture de session, et chacune faisait son 'git fetch' : un fetch
concurrent reecrivait FETCH_HEAD entre la mesure du retard et le merge, qui
fusionnait alors une ref deja contenue dans HEAD ("Already up to date",
exit 0). D'ou trois regles :

1. Le distant est fetche dans une ref privee (REF_DEPLOIEMENT), que rien
   d'autre n'ecrit, et on fusionne le sha mesure, jamais FETCH_HEAD.
2. Apres le merge, HEAD doit valoir ce sha, sinon c'est un echec.
3. Un verrou fichier (deploy/logs/pull.lock) serialise les pulls : la tache
   qui arrive en second attend, puis constate qu'elle est deja a jour. C'est
   ce qui garantit que FUSEAU_Daily_ETL lit le gsheet avec le code du jour.

Junior Tip : une ref privee sous refs/fuseau/ marche aussi quand la cible est
un tag (un tag ne met pas a jour origin/<nom>), et n'apparait ni dans
'git branch' ni dans 'git tag'.

Seul point de pull du poste. Utilise par run_api.py, et en ligne de commande
par les taches planifiees (run_etl_scheduled.ps1, run_daily_etl.ps1) :
    python -m src.utils.git_sync --origine FUSEAU_Files_ETL
Code de sortie 0 si le code est celui de la branche cible, 2 sinon.
"""
from __future__ import annotations

import argparse
import logging
import os
import subprocess
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

STATUT_A_JOUR = "a_jour"
STATUT_MIS_A_JOUR = "mis_a_jour"
STATUT_BLOQUE = "bloque"
STATUT_ECHEC = "echec"

NOM_MARQUEUR = "PULL_BLOQUE.txt"
NOM_VERROU = "pull.lock"
REF_DEPLOIEMENT = "refs/fuseau/deploiement"

# Un pull normal dure une dizaine de secondes. Au-dela de 3 minutes d'attente,
# on renonce plutot que de retenir l'ETL du jour ; un verrou de plus de 10
# minutes vient d'un processus tue en cours de route et peut etre repris.
ATTENTE_VERROU_S = 180.0
VERROU_PERIME_S = 600.0

EXIT_OK = 0
EXIT_PULL_KO = 2


class VerrouOccupeError(RuntimeError):
    """Un autre processus tient le verrou de pull au-dela du delai d'attente."""


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
    origine: str = ""

    @property
    def ok(self) -> bool:
        """Vrai si le code local est celui de la branche cible."""
        return self.statut in (STATUT_A_JOUR, STATUT_MIS_A_JOUR)


def chemin_marqueur(racine: Path) -> Path:
    """Emplacement du marqueur, dans deploy/logs (deja couvert par le .gitignore)."""
    return racine / "deploy" / "logs" / NOM_MARQUEUR


def chemin_verrou(racine: Path) -> Path:
    """Emplacement du verrou de pull, a cote du marqueur."""
    return racine / "deploy" / "logs" / NOM_VERROU


@contextmanager
def verrou_pull(
    racine: Path,
    attente_max_s: float = ATTENTE_VERROU_S,
    perime_s: float = VERROU_PERIME_S,
    pas_s: float = 1.0,
) -> Iterator[None]:
    """
    Verrou inter-processus autour du pull, par creation exclusive d'un fichier.

    Junior Tip : os.O_CREAT | os.O_EXCL echoue de facon atomique si le fichier
    existe deja, sous Windows comme sous Linux. C'est le verrou le plus simple
    qui tienne entre deux taches planifiees lancees a la meme seconde.

    Raises:
        VerrouOccupeError: le verrou est tenu au-dela de attente_max_s.
    """
    verrou = chemin_verrou(racine)
    verrou.parent.mkdir(parents=True, exist_ok=True)
    debut = time.monotonic()
    attente_annoncee = False
    while True:
        try:
            fd = os.open(verrou, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            break
        except FileExistsError:
            try:
                age = time.time() - verrou.stat().st_mtime
            except FileNotFoundError:
                continue  # libere entre-temps, on retente aussitot
            if age > perime_s:
                logger.warning("[GIT] [ATTENTION] Verrou de pull perime (%.0f s), repris : %s", age, verrou)
                verrou.unlink(missing_ok=True)
                continue
            if time.monotonic() - debut > attente_max_s:
                raise VerrouOccupeError(
                    f"verrou {verrou} tenu depuis plus de {attente_max_s:.0f} s par un autre pull"
                ) from None
            if not attente_annoncee:
                logger.info("[GIT] [INFO] Un autre pull est en cours, attente du verrou...")
                attente_annoncee = True
            time.sleep(pas_s)
    try:
        os.write(fd, f"pid={os.getpid()} {datetime.now():%Y-%m-%d %H:%M:%S}\n".encode("ascii"))
        os.close(fd)
        yield
    finally:
        verrou.unlink(missing_ok=True)


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


def _sha_complet(racine: Path, ref: str) -> str | None:
    res = _git(racine, "rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}")
    return res.stdout.strip() if res.returncode == 0 and res.stdout.strip() else None


def ecrire_marqueur(racine: Path, resultat: ResultatSync) -> Path:
    """Ecrit le marqueur PULL_BLOQUE.txt, lisible par un non-developpeur."""
    marqueur = chemin_marqueur(racine)
    marqueur.parent.mkdir(parents=True, exist_ok=True)
    lignes = [
        "PULL AUTOMATIQUE BLOQUE : le poste ne tourne PAS sur le code de la branche cible.",
        f"Horodatage   : {datetime.now():%Y-%m-%d %H:%M:%S}",
        f"Origine      : {resultat.origine or 'inconnue'}",
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


def _conclure(racine: Path, resultat: ResultatSync) -> ResultatSync:
    """Pose ou retire le marqueur selon l'issue, et journalise un echec."""
    if resultat.ok:
        chemin_marqueur(racine).unlink(missing_ok=True)
    else:
        marqueur = ecrire_marqueur(racine, resultat)
        logger.error("[GIT] [ECHEC] Pull bloque (%s) : %s. Marqueur : %s",
                     resultat.statut, resultat.message, marqueur)
        for fichier in resultat.fichiers:
            logger.error("[GIT] [ATTENTION]   fichier en cause : %s", fichier)
    return resultat


def _synchroniser_sous_verrou(racine: Path, branche: str, origine: str) -> ResultatSync:
    head_avant = _head_court(racine)

    def _echec(message: str, distant: str | None = None, retard: int | None = None) -> ResultatSync:
        return ResultatSync(STATUT_ECHEC, branche, head_avant, head_avant, distant, retard,
                            message=message, origine=origine)

    # Le '+' autorise la ref privee a reculer si la branche distante a ete
    # reecrite : on veut le distant tel qu'il est, le --ff-only protege le poste.
    fetch = _git(racine, "fetch", "--no-tags", "origin", f"+{branche}:{REF_DEPLOIEMENT}", timeout=60)
    if fetch.returncode != 0:
        return _echec(f"fetch impossible : {_sortie(fetch)}")

    cible = _sha_complet(racine, REF_DEPLOIEMENT)
    if cible is None:
        return _echec(f"ref {REF_DEPLOIEMENT} illisible apres le fetch")
    distant = cible[:7]
    compte = _git(racine, "rev-list", "--count", f"HEAD..{cible}")
    retard = int(compte.stdout.strip()) if compte.returncode == 0 else None
    logger.info("[GIT] [INFO] %s distant : %s, retard du poste : %s commit(s)",
                branche, distant, retard if retard is not None else "inconnu")

    statut = _git(racine, "status", "--porcelain", "--untracked-files=no")
    fichiers = fichiers_suivis_modifies(statut.stdout)
    if fichiers:
        return ResultatSync(
            STATUT_BLOQUE, branche, head_avant, head_avant, distant, retard, fichiers,
            message="fichiers suivis modifies localement, pull annule", origine=origine,
        )

    if retard == 0:
        logger.info("[GIT] [SUCCES] Deja a jour sur %s (%s).", branche, head_avant)
        return ResultatSync(STATUT_A_JOUR, branche, head_avant, head_avant, distant, retard,
                            origine=origine)

    merge = _git(racine, "merge", "--ff-only", cible)
    if merge.returncode != 0:
        # Cas typique : un fichier non suivi collisionne avec un fichier
        # ajoute par le distant, ou des commits locaux divergent.
        return _echec(f"merge --ff-only refuse : {_sortie(merge)}", distant, retard)

    # Controle final : un merge a exit 0 ne prouve pas que HEAD a bouge. C'est
    # exactement ce qui a produit le faux [SUCCES] du 08/10.
    if _sha_complet(racine, "HEAD") != cible:
        return _echec(
            f"merge annonce reussi mais HEAD ({_head_court(racine)}) != distant ({distant})",
            distant, retard,
        )

    head_apres = _head_court(racine)
    logger.info("[GIT] [SUCCES] Code mis a jour : %s -> %s", head_avant, head_apres)
    return ResultatSync(STATUT_MIS_A_JOUR, branche, head_avant, head_apres, distant, retard,
                        origine=origine)


def synchroniser(
    racine: Path,
    branche: str,
    origine: str = "",
    attente_verrou_s: float = ATTENTE_VERROU_S,
) -> ResultatSync:
    """
    Met le depot a jour en avance rapide sur origin/<branche>.

    Ne leve jamais : l'appelant doit pouvoir continuer sur le code local. Le
    marqueur est ecrit ou supprime selon l'issue, et chaque etape est
    journalisee avec le sha court avant/apres.

    Args:
        racine: racine du depot a mettre a jour.
        branche: branche ou tag cible (BRANCHE_DEPLOIEMENT).
        origine: appelant, recopie dans le marqueur pour savoir quelle tache a bloque.
        attente_verrou_s: attente maximale si un autre pull tient le verrou.
    """
    head_avant = _head_court(racine)
    logger.info("[GIT] [INFO] HEAD local avant synchro : %s (cible %s)", head_avant, branche)
    try:
        with verrou_pull(racine, attente_max_s=attente_verrou_s):
            resultat = _synchroniser_sous_verrou(racine, branche, origine)
    except VerrouOccupeError as exc:
        resultat = ResultatSync(STATUT_ECHEC, branche, head_avant, head_avant,
                                message=str(exc), origine=origine)
    except (OSError, subprocess.SubprocessError, ValueError) as exc:
        resultat = ResultatSync(STATUT_ECHEC, branche, head_avant, head_avant,
                                message=f"synchronisation impossible : {exc}", origine=origine)
    return _conclure(racine, resultat)


def main(argv: list[str] | None = None) -> int:
    """
    Point d'entree des taches planifiees.

    La branche vient de Config.BRANCHE_DEPLOIEMENT (config/.env), comme pour
    run_api.py : les scripts PowerShell ne lisaient que la variable
    d'environnement et pouvaient viser une autre cible que l'API.
    """
    from src.utils.config_manager import Config
    from src.utils.logging_setup import setup_logging

    setup_logging()
    parser = argparse.ArgumentParser(description="Pull en avance rapide du poste FUSEAU.")
    parser.add_argument("--origine", default="", help="Nom de la tache appelante, recopie dans le marqueur.")
    parser.add_argument("--branche", default=Config.BRANCHE_DEPLOIEMENT, help="Branche ou tag cible.")
    args = parser.parse_args(argv)

    racine = Path(__file__).resolve().parents[2]
    resultat = synchroniser(racine, args.branche, origine=args.origine)
    logger.info("[GIT] [INFO] HEAD local apres synchro (code execute) : %s", _head_court(racine))
    return EXIT_OK if resultat.ok else EXIT_PULL_KO


if __name__ == "__main__":
    raise SystemExit(main())
