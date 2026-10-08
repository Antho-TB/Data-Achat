# -*- coding: utf-8 -*-
"""
[API]
=============================================================================
FACTURATION INTERSITE DES ANALYSES QUALITE (SE <-> CIE), LECTURE SEULE
=============================================================================

Besoin metier (Maxence BRUN, 08/10/2026, BUG-007) : chaque analyse qualite est
une commande d'achat SE adressee a TARRERIAS ET CIE (la "CA", reference
"PO/STADE"). CIE la livre par un BL, puis les deux societes facturent. Maxence
compare aujourd'hui a la main, dans le gsheet SUIVI DES ANALYSES, le BL qualite
de CIE et la commande SE : si les montants concordent, la ligne passe "a
facturer", puis "facturation faite". Le probleme qu'il rencontre : des BL CIE
qui ne remontent pas vers SE.

Ce module reconstruit ce rapprochement depuis Sylob (source de verite), via les
copies MyReport que l'API lit dans dtpf_sylob_prod :
  CA SE (commandes, lignes de prestation)
    -> commande de vente CIE (identifiant_edi = n° de CA)
    -> lignes de commande de vente
    -> lignes de BL CIE (ligne_id_lignecommandevente)
Le rapprochement est exact, ligne a ligne, et non par montant ou par reference :
une meme reference "PO/STADE" porte souvent plusieurs CA et plusieurs BL.

Lecture seule : aucune saisie. Les cases "a facturer" et "facturation faite" du
gsheet ne sont pas reprises ici ; la colonne de statut les remplace par ce que
dit Sylob.
"""
from __future__ import annotations

import re
from datetime import date, timedelta
from typing import Any, Optional

from src.utils.config_manager import Config

# Au-dela de ce delai sans BL CIE, la CA est signalee : c'est le cas que Maxence
# rencontre (BL non remonte). En deca, l'analyse est simplement en cours.
DELAI_BL_JOURS = 30
# Tolerance d'arrondi entre le montant de la CA et la somme des lignes du BL.
TOLERANCE_MONTANT = 0.01

STATUT_ATTENTE_BL = "attente_bl"
STATUT_BL_MANQUANT = "bl_manquant"
STATUT_ECART = "ecart"
STATUT_A_FACTURER = "a_facturer"
STATUT_FACTUREE = "facturee"

RE_PO = re.compile(r"(\d{5,8})")
STADES = (("RECEP", "RECEP"), ("SEMI", "SP"), ("SP", "SP"), ("MAT", "MAT"), ("BAT", "BAT"))


def _table(nom: str) -> str:
    return f'"{Config.MYREPORT_SCHEMA}"."{nom}"'


def sql_facturation() -> str:
    """
    Requete de rapprochement CA SE / BL CIE, une ligne par CA.

    Junior Tip : les noms de tables MyReport viennent de la configuration.
    MyReport renumerote ses tables (commandes2, commandes6...) et va passer du
    schema public au schema myreport : ce doit etre une ligne de configuration,
    pas une modification de code.
    """
    return f"""
    WITH ca AS (
        SELECT h.commande_numero_de_la_commande AS ca,
               h.commande_creee_le::date        AS date_ca,
               h.commande_reference             AS reference,
               h.commande_total_ht              AS montant_ca,
               h.commande_etat_de_facturation   AS etat_facturation_se
        FROM {_table(Config.MYREPORT_TABLE_COMMANDES)} h
        WHERE h.database_name = 'SE'
          AND h.frn_raison_sociale = 'TARRERIAS ET CIE'
          AND h.commande_creee_le >= :depuis
    ),
    lignes_ca AS (
        SELECT d.commande_numero_de_la_commande AS ca,
               CASE
                   WHEN d.ligne_designation ILIKE '%SPECTRO%' THEN 'S'
                   WHEN d.ligne_designation ILIKE '%DURET%' THEN 'D'
                   WHEN d.ligne_designation ILIKE '%MECA%' OR d.ligne_designation ILIKE '%MÉCA%' THEN 'M'
                   WHEN d.ligne_designation ILIKE '%CYCLE%' THEN 'C'
                   WHEN d.ligne_designation ILIKE '%RAPPORT%' THEN 'R'
               END AS presta,
               d.ligne_quantite, d.ligne_commentaire
        FROM {_table(Config.MYREPORT_TABLE_COMMANDES_DETAIL)} d
        JOIN ca ON ca.ca = d.commande_numero_de_la_commande
        WHERE d.database_name = 'SE'
    ),
    ca_presta AS (
        SELECT ca,
               SUM(ligne_quantite) FILTER (WHERE presta = 'S') AS qte_s,
               SUM(ligne_quantite) FILTER (WHERE presta = 'D') AS qte_d,
               SUM(ligne_quantite) FILTER (WHERE presta = 'M') AS qte_m,
               SUM(ligne_quantite) FILTER (WHERE presta = 'C') AS qte_c,
               SUM(ligne_quantite) FILTER (WHERE presta = 'R') AS qte_r,
               COUNT(*) FILTER (WHERE presta IS NOT NULL) AS nb_presta,
               MAX(substring(ligne_commentaire from '^([0-9]{{6,8}})')) AS ref_article
        FROM lignes_ca GROUP BY ca
    ),
    cie AS (
        SELECT v.commande_identifiant_edi AS ca, v.commande_id_commandevente AS id_cde_vente,
               v.commande_total_ht AS montant_cie
        FROM {_table(Config.MYREPORT_TABLE_VENTES)} v
        JOIN ca ON ca.ca = v.commande_identifiant_edi
        WHERE v.database_name = 'CIE'
    ),
    bl_lignes AS (
        SELECT cie.ca, l.livraison_livraison, l.ligne_total_ht
        FROM cie
        JOIN {_table(Config.MYREPORT_TABLE_VENTES_DETAIL)} dv
          ON dv.database_name = 'CIE' AND dv.ligne_id_commandevente = cie.id_cde_vente
        JOIN {_table(Config.MYREPORT_TABLE_LIVRAISONS_DETAIL)} l
          ON l.database_name = 'CIE' AND l.ligne_id_lignecommandevente = dv.ligne_id_lignecommandevente
    ),
    bl AS (
        SELECT b.ca,
               STRING_AGG(DISTINCT b.livraison_livraison, ', ') AS bl,
               SUM(b.ligne_total_ht) AS montant_bl,
               MAX(h.livraison_livree_le)::date AS date_bl,
               BOOL_AND(h.livraison_etat_de_facturation ILIKE 'termin%') AS bl_factures
        FROM bl_lignes b
        LEFT JOIN {_table(Config.MYREPORT_TABLE_LIVRAISONS)} h
          ON h.database_name = 'CIE' AND h.livraison_livraison = b.livraison_livraison
        GROUP BY b.ca
    )
    SELECT ca.ca, ca.date_ca, ca.reference, ca.montant_ca, ca.etat_facturation_se,
           p.qte_s, p.qte_d, p.qte_m, p.qte_c, p.qte_r, p.ref_article,
           cie.montant_cie, bl.bl, bl.date_bl, bl.montant_bl, bl.bl_factures
    FROM ca
    JOIN ca_presta p ON p.ca = ca.ca AND p.nb_presta > 0
    LEFT JOIN cie ON cie.ca = ca.ca
    LEFT JOIN bl ON bl.ca = ca.ca
    ORDER BY ca.date_ca DESC, ca.ca DESC
    """


def decouper_reference(reference: Optional[str]) -> tuple[Optional[str], Optional[str]]:
    """
    Extrait le PO fournisseur et le stade d'une reference de CA ("00187132/BAT").

    Junior Tip : la reference est saisie a la main. On y trouve "RECEPTION",
    "SEMI PROD", "MATIERE", plusieurs PO ("173654-177438") : on prend le premier
    PO et le premier stade reconnu, et on laisse None plutot que de deviner.

    Returns:
        (po sans zeros de tete, stade parmi MAT / SP / BAT / RECEP), chacun None
        si introuvable.
    """
    ref = (reference or "").upper()
    m = RE_PO.search(ref)
    po = m.group(1).lstrip("0") if m else None
    stade = next((code for motif, code in STADES if motif in ref), None)
    return po, stade


def statut_facturation(ligne: dict[str, Any], aujourd_hui: date) -> str:
    """
    Classe une CA selon l'etat du rapprochement SE / CIE, dans l'ordre du
    processus de Maxence : BL attendu, montants comparables, facturation.

    Args:
        ligne: une ligne de sql_facturation().
        aujourd_hui: date de reference, pour le delai sans BL.

    Returns:
        attente_bl, bl_manquant, ecart, a_facturer ou facturee.
    """
    if not ligne.get("bl"):
        date_ca = ligne.get("date_ca")
        if date_ca and date_ca < aujourd_hui - timedelta(days=DELAI_BL_JOURS):
            return STATUT_BL_MANQUANT
        return STATUT_ATTENTE_BL
    montant_ca = float(ligne.get("montant_ca") or 0)
    montant_bl = float(ligne.get("montant_bl") or 0)
    if abs(montant_bl - montant_ca) > TOLERANCE_MONTANT:
        return STATUT_ECART
    se_facturee = str(ligne.get("etat_facturation_se") or "").lower().startswith("termin")
    if se_facturee and ligne.get("bl_factures"):
        return STATUT_FACTUREE
    return STATUT_A_FACTURER


def enrichir(lignes: list[dict[str, Any]], aujourd_hui: date) -> list[dict[str, Any]]:
    """Ajoute PO, stade, statut et ecart de montant a chaque CA."""
    for ligne in lignes:
        ligne["po_number"], ligne["stade"] = decouper_reference(ligne.get("reference"))
        ligne["statut"] = statut_facturation(ligne, aujourd_hui)
        if ligne.get("montant_bl") is not None:
            ligne["ecart_montant"] = round(
                float(ligne["montant_bl"]) - float(ligne.get("montant_ca") or 0), 2)
        else:
            ligne["ecart_montant"] = None
    return lignes
