# -*- coding: utf-8 -*-
"""
Droits par onglet (docs/20261008_FUSEAU_Cadrage_DroitsOnglets_FichesAchat_v1.md).

Le profil vient des roles d'application Entra, transmis par Easy Auth dans
l'en-tete X-MS-CLIENT-PRINCIPAL (decision d'Antho du 08/10). Les roles sont
affectes aux personnes dans l'application d'entreprise « FUSEAU - Dashboard
Achats » : aucune table de droits dans FUSEAU.

Le controle porte sur l'API, pas seulement sur l'interface : masquer un onglet
laisserait /api/previsionnel lisible en tapant l'URL. Chaque route /api est
rattachee a un ou plusieurs onglets (REGLES) ; une route absente de REGLES est
refusee en mode bloquant, pour qu'un nouvel endpoint ne reste pas ouvert par oubli.

Trois modes (Config.DROITS_MODE) :
- off      : aucun controle (retour arriere) ;
- journal  : rien n'est bloque ni masque, les acces qui seraient refuses sont
             journalises. Mode de mise en route, le temps d'affecter les roles ;
- bloquant : 403 hors profil, montants retires des reponses JSON pour les
             profils qui ne les voient pas.
"""
from __future__ import annotations

import base64
import binascii
import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Optional

logger = logging.getLogger(__name__)

TOUS_LES_ONGLETS: frozenset[str] = frozenset({
    "dashboard", "commandes", "fournisseurs", "artwork", "previsionnel",
    "conteneurs", "qualite", "article", "fiche",
})

# Valeur du role Entra -> (onglets, voit les montants). Valide par Antho le 08/10.
PROFILS: dict[str, tuple[frozenset[str], bool]] = {
    "Achats": (TOUS_LES_ONGLETS, True),
    "Supply": (frozenset({"commandes", "conteneurs", "previsionnel", "fournisseurs"}), False),
    "Design": (frozenset({"artwork", "article", "fiche"}), False),
    "Qualite": (frozenset({"qualite", "artwork", "article"}), False),
}

# Permissions fines, portees par un role Entra dedie (pas par un profil).
PERMISSIONS: dict[str, str] = {
    "Artwork.Archiver": "artwork.archiver",  # « descente » reservee a Maxence (08/10)
}

PUBLIC = "public"      # sans controle (sonde de sante de la plateforme)
CONNECTE = "connecte"  # tout utilisateur qui a au moins un onglet

# (methode, motif du chemin) -> onglets dont l'un suffit, ou PUBLIC / CONNECTE,
# ou "perm:<permission>". La premiere regle qui correspond s'applique.
REGLES: list[tuple[str, re.Pattern[str], frozenset[str] | str]] = [
    (m, re.compile(p), o) for m, p, o in [
        ("GET", r"^/api/health$", PUBLIC),
        ("GET", r"^/api/moi$", PUBLIC),  # le refus doit pouvoir s'afficher
        ("GET", r"^/api/sante/sources$", CONNECTE),
        ("GET", r"^/api/search/article$", CONNECTE),
        ("GET", r"^/api/kpis$", frozenset({"dashboard"})),
        ("GET", r"^/api/commandes$", frozenset({"commandes", "dashboard", "article", "fiche"})),
        ("PUT", r"^/api/commandes/[^/]+/[^/]+$", frozenset({"commandes"})),
        ("PUT", r"^/api/paiement/conteneur/[^/]+$", frozenset({"conteneurs"})),
        ("GET", r"^/api/conteneurs$", frozenset({"conteneurs", "dashboard"})),
        ("GET", r"^/api/fournisseurs$", frozenset({"fournisseurs"})),
        ("GET", r"^/api/fournisseurs/[^/]+/historique-prix$", frozenset({"fournisseurs", "article"})),
        ("GET", r"^/api/produit/[^/]+$", frozenset({"article", "fiche"})),
        ("POST", r"^/api/fiche-achat/export-excel$", frozenset({"fiche"})),
        ("GET", r"^/api/qualite(/[a-z_-]+)?$", frozenset({"qualite"})),
        ("GET", r"^/api/previsionnel(/mesures)?$", frozenset({"previsionnel"})),
        ("GET", r"^/api/artwork$", frozenset({"artwork"})),
        ("PUT", r"^/api/artwork/[^/]+$", frozenset({"artwork"})),
        ("POST", r"^/api/artworks/[^/]+/archiver$", "perm:artwork.archiver"),
        ("GET", r"^/api/artworks(/mode|/[^/]+/historique)?$", frozenset({"artwork"})),
        ("POST", r"^/api/artworks(/[^/]+/valider)?$", frozenset({"artwork"})),
        ("PATCH", r"^/api/artworks/[^/]+$", frozenset({"artwork"})),
    ]
]

# Cles JSON retirees pour un profil sans montants : prix, montants, valeurs.
# Motif plutot que liste : un nouveau champ « prix_xxx » est masque d'office.
MOTIF_MONTANT = re.compile(r"(^|_)(prix|montant|montants|valeur|cout|tarif|cash)(_|$)")


@dataclass(frozen=True)
class Droits:
    identite: str
    roles: frozenset[str]
    onglets: frozenset[str]
    montants: bool
    permissions: frozenset[str] = field(default_factory=frozenset)

    def autorise(self, regle: frozenset[str] | str) -> bool:
        if regle == PUBLIC:
            return True
        if regle == CONNECTE:
            return bool(self.onglets)
        if isinstance(regle, str) and regle.startswith("perm:"):
            return regle[5:] in self.permissions
        return bool(self.onglets & regle)  # type: ignore[operator]


ACCES_COMPLET = Droits("poste-metier", frozenset(), TOUS_LES_ONGLETS, True,
                       frozenset(PERMISSIONS.values()))


def roles_du_principal(entete: str) -> frozenset[str]:
    """
    Roles d'application lus dans X-MS-CLIENT-PRINCIPAL (JSON en base64).

    Junior Tip : Easy Auth range les roles parmi les « claims », sous le type
    annonce par role_typ (URI longue) ou sous « roles » selon le jeton. On
    accepte les deux. Un en-tete illisible donne zero role : refus, pas plantage.
    """
    if not entete:
        return frozenset()
    try:
        principal = json.loads(base64.b64decode(entete + "=" * (-len(entete) % 4)))
    except (binascii.Error, ValueError, UnicodeDecodeError):
        logger.warning("[ATTENTION] [DROITS] En-tete X-MS-CLIENT-PRINCIPAL illisible.")
        return frozenset()
    types = {"roles", principal.get("role_typ") or "roles"}
    return frozenset(c.get("val", "") for c in principal.get("claims") or []
                     if c.get("typ") in types and c.get("val"))


def droits_depuis_roles(identite: str, roles: frozenset[str]) -> Droits:
    onglets: set[str] = set()
    montants = False
    for role in roles:
        if role in PROFILS:
            o, m = PROFILS[role]
            onglets |= o
            montants = montants or m
    permissions = frozenset(PERMISSIONS[r] for r in roles if r in PERMISSIONS)
    return Droits(identite, roles, frozenset(onglets), montants, permissions)


def regle_pour(methode: str, chemin: str) -> Optional[frozenset[str] | str]:
    """Regle de la route, ou None si la route /api n'est pas declaree."""
    for m, motif, regle in REGLES:
        if m == methode and motif.match(chemin):
            return regle
    return None


def masquer_montants(donnees: Any) -> Any:
    """Retire recursivement les cles de montant d'une reponse JSON."""
    if isinstance(donnees, dict):
        return {k: masquer_montants(v) for k, v in donnees.items()
                if not MOTIF_MONTANT.search(str(k).lower())}
    if isinstance(donnees, list):
        return [masquer_montants(v) for v in donnees]
    return donnees
