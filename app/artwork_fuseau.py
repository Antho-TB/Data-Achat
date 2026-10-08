# -*- coding: utf-8 -*-
"""
[API]
=============================================================================
ARTWORKS SAISIS DANS FUSEAU (premier domaine de la phase d'ecriture)
=============================================================================

Retours de la demo du 06/10 (Clarisse, Maxence) : un identifiant par artwork,
plusieurs artworks par article, trois dates (creation, validation, mise a
jour), saisie et modification dans FUSEAU, archivage par un clic de Maxence.

Le domaine s'allume avec ECRITURE_ARTWORK=1 (app setting), apres la migration
sql/20261008_socle_ecriture.sql et la reprise du gsheet
(src/scripts/etl/reprise_artwork_gsheet.py). Eteint, toutes les routes
d'ecriture repondent 409 et l'onglet continue de lire le miroir du gsheet
(/api/artwork) : le code peut etre deploye avant les tables.
"""
from __future__ import annotations

from datetime import date
from typing import Any, Callable, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import text

from app.ecriture import (
    ConflitVersion,
    LigneIntrouvable,
    creer,
    historique,
    identifiant_artwork,
    modifier,
)
from src.utils.config_manager import Config

SCHEMA = Config.PG_SCHEMA
TABLE = "artwork"
STATUTS = ("en_attente", "valide", "archive")
CHAMPS_MODIFIABLES = (
    "designation", "code_article", "priorite", "valideur", "commentaire_acheteur",
    "commentaire_design", "commentaire_version", "lien_drive", "date_demande",
    "date_derniere_version",
)


class ArtworkCreation(BaseModel):
    designation: str = Field(min_length=1, max_length=300)
    code_article: Optional[str] = Field(default=None, max_length=60)
    priorite: Optional[int] = Field(default=None, ge=1, le=5)
    valideur: Optional[str] = Field(default=None, max_length=80)
    commentaire_acheteur: Optional[str] = Field(default=None, max_length=2000)
    commentaire_design: Optional[str] = Field(default=None, max_length=2000)
    lien_drive: Optional[str] = Field(default=None, max_length=500)
    date_demande: Optional[date] = None


class ArtworkModification(BaseModel):
    version: int = Field(ge=1)
    designation: Optional[str] = Field(default=None, min_length=1, max_length=300)
    code_article: Optional[str] = Field(default=None, max_length=60)
    priorite: Optional[int] = Field(default=None, ge=1, le=5)
    valideur: Optional[str] = Field(default=None, max_length=80)
    commentaire_acheteur: Optional[str] = Field(default=None, max_length=2000)
    commentaire_design: Optional[str] = Field(default=None, max_length=2000)
    commentaire_version: Optional[str] = Field(default=None, max_length=2000)
    lien_drive: Optional[str] = Field(default=None, max_length=500)
    date_demande: Optional[date] = None
    date_derniere_version: Optional[date] = None


class Version(BaseModel):
    version: int = Field(ge=1)


def ecriture_active() -> bool:
    return Config.ECRITURE_ARTWORK


def _exiger_actif() -> None:
    if not ecriture_active():
        raise HTTPException(status_code=409, detail=(
            "La saisie des artworks dans FUSEAU n'est pas encore activée : "
            "les artworks se modifient dans le gsheet de Clarisse."))


def _serialiser(ligne: dict[str, Any]) -> dict[str, Any]:
    return {k: (v.isoformat() if hasattr(v, "isoformat") else v) for k, v in ligne.items()}


def construire_router(require_utilisateur: Callable[..., str], get_engine: Callable[[], Any]) -> APIRouter:
    """
    Routes /api/artworks. Les dependances sont injectees par app.main pour
    eviter un import circulaire (identite Entra, moteur SQL).
    """
    router = APIRouter(prefix="/api/artworks", tags=["artworks"])

    def _traduire(exc: Exception) -> HTTPException:
        if isinstance(exc, ConflitVersion):
            return HTTPException(status_code=409, detail={
                "message": (f"Cet artwork a été modifié entre-temps par {exc.actuelle.get('maj_par')}. "
                            "Rechargez pour voir sa version actuelle avant de modifier."),
                "actuelle": _serialiser(exc.actuelle)})
        if isinstance(exc, LigneIntrouvable):
            return HTTPException(status_code=404, detail="Artwork introuvable.")
        if isinstance(exc, ValueError):
            return HTTPException(status_code=400, detail=str(exc))
        raise exc

    @router.get("/mode")
    def mode() -> dict[str, Any]:
        """Indique au front si la saisie est active (sinon : lecture du gsheet)."""
        return {"ecriture": ecriture_active()}

    @router.get("")
    def lister(statut: Optional[str] = Query(None)) -> dict[str, Any]:
        _exiger_actif()
        if statut and statut not in STATUTS:
            raise HTTPException(status_code=400, detail=f"Statut inconnu. Valeurs : {STATUTS}")
        with get_engine().connect() as conn:
            lignes = conn.execute(text(f"""
                SELECT a.*,
                       (SELECT string_agg(DISTINCT c.po_number, ', ' ORDER BY c.po_number)
                          FROM {SCHEMA}.commande c WHERE c.code_article = a.code_article) AS po_number
                FROM {SCHEMA}.artwork a
                WHERE (:statut IS NULL OR a.statut = :statut)
                ORDER BY a.statut, a.priorite NULLS LAST, a.maj_le DESC
            """), {"statut": statut}).mappings().all()
        return {"data": [_serialiser(dict(l)) for l in lignes], "ecriture": True}

    @router.post("")
    def creer_artwork(payload: ArtworkCreation, auteur: str = Depends(require_utilisateur)) -> dict[str, Any]:
        _exiger_actif()
        aujourdhui = date.today()
        with get_engine().begin() as conn:
            prefixe = f"{(payload.code_article or 'NOUVEAU').strip().upper()}-{aujourdhui:%Y%m%d}"
            existants = [r[0] for r in conn.execute(text(f"""
                SELECT identifiant FROM {SCHEMA}.artwork WHERE identifiant LIKE :p
            """), {"p": prefixe + "%"})]
            valeurs = payload.model_dump()
            valeurs.update({
                "identifiant": identifiant_artwork(payload.code_article, aujourdhui, existants),
                "statut": "en_attente", "cree_par": auteur, "maj_par": auteur,
                "date_demande": payload.date_demande or aujourdhui,
            })
            ligne = creer(conn, TABLE, valeurs, auteur, cle_col="identifiant")
        return _serialiser(ligne)

    @router.patch("/{identifiant}")
    def modifier_artwork(identifiant: str, payload: ArtworkModification,
                         auteur: str = Depends(require_utilisateur)) -> dict[str, Any]:
        _exiger_actif()
        changements = payload.model_dump(exclude_unset=True)
        version = changements.pop("version")
        try:
            with get_engine().begin() as conn:
                ligne = modifier(conn, TABLE, "identifiant", identifiant, changements,
                                 version, auteur, CHAMPS_MODIFIABLES)
        except (ConflitVersion, LigneIntrouvable, ValueError) as exc:
            raise _traduire(exc)
        return _serialiser(ligne)

    def _changer_statut(identifiant: str, version: int, auteur: str, statut: str,
                        champs_date: tuple[str, str], action: str) -> dict[str, Any]:
        champ_le, champ_par = champs_date
        try:
            with get_engine().begin() as conn:
                ligne = modifier(conn, TABLE, "identifiant", identifiant,
                                 {"statut": statut, champ_le: date.today(), champ_par: auteur},
                                 version, auteur, ("statut", champ_le, champ_par), action=action)
        except (ConflitVersion, LigneIntrouvable, ValueError) as exc:
            raise _traduire(exc)
        return _serialiser(ligne)

    @router.post("/{identifiant}/valider")
    def valider(identifiant: str, payload: Version, auteur: str = Depends(require_utilisateur)) -> dict[str, Any]:
        """Clarisse valide l'artwork : il passe dans la liste, en attente d'archivage."""
        _exiger_actif()
        return _changer_statut(identifiant, payload.version, auteur, "valide",
                               ("valide_le", "valide_par"), "modification")

    @router.post("/{identifiant}/archiver")
    def archiver(identifiant: str, payload: Version, auteur: str = Depends(require_utilisateur)) -> dict[str, Any]:
        """Maxence archive l'artwork apres verification (clic manuel, decision du 08/10)."""
        _exiger_actif()
        return _changer_statut(identifiant, payload.version, auteur, "archive",
                               ("archive_le", "archive_par"), "archivage")

    @router.get("/{identifiant}/historique")
    def historique_artwork(identifiant: str) -> dict[str, Any]:
        _exiger_actif()
        with get_engine().connect() as conn:
            lignes = historique(conn, TABLE, identifiant)
        return {"data": [_serialiser(l) for l in lignes]}

    return router
