# -*- coding: utf-8 -*-
"""
[ETL]
=============================================================================
ENRICHISSEMENT CA FOURNISSEUR - 3 ANS (Sylob 3 societes)
=============================================================================

Enrichissement de achat.fournisseur_ca : CA achats cumule sur 3 ans par fournisseur.

Mappe nos noms de fournisseurs (achat.commande, texte libre) vers les codes Sylob
via le join PO (commande_numero_de_la_commande zero-padde 8 = po_number), puis somme
commande_total_ht sur 3 ans glissants, UNION des 3 societes (GDD, SE, Cie).
Montant en devise commande (USD pour les imports). Lecture seule Sylob ; FULL REFRESH cote achat.

Dedoublonnage (decision metier 23/07) : la cle de regroupement est l'ID Sylob
`frn_code_fournisseur`, jamais le nom texte libre saisi cote achat.commande. Deux
noms differents partageant le meme frn_code (ex. GUANGWEI / DIAMOND TRACK) sont
de VRAIS doublons -- ils sont fusionnes en une seule ligne (composantes connexes
nom<->code, cf. _group_by_frn_code) plutot que d'apparaitre comme 2 fournisseurs
recevant chacun le CA complet.

⚠️ Garde-fou anti-faux-positif : le filtre MIN_PO_SUPPORT ne s'applique QUE quand
un nom a plusieurs codes candidats (ambiguite reelle) -- un nom avec un seul code,
meme vu sur 1 seul PO (cas frequent : POLLYDA, WANSHENG... peu de volume importe),
est conserve tel quel. Verifie empiriquement le 23/07 -- un seul PO ("SE 00166337",
texte fournisseur "GUANGWEI") pointait par erreur vers le frn_code de HONGXING
(00001217, 29 PO par ailleurs) alors que GUANGWEI a 14 PO sur son vrai code
(00001220, partage avec DIAMOND TRACK). Sans ce filtre, le Union-Find fusionnait
a tort GUANGWEI/DIAMOND TRACK avec HONGXING (2 fournisseurs bien distincts) a
cause de cette unique ligne de saisie bruitee. Un filtre uniforme (sans distinguer
"nom ambigu" de "nom a faible volume") ferait a tort disparaitre POLLYDA & co.

Alias connus (source humaine, pas de detection automatique possible) : le
questionnaire de passation d'Andrea (`docs/20260721_FicheAchat_Questionnaire_
Sourcing_Andrea_v1.docx`, §6 "Pieges recurrents") liste des synonymes de
fournisseur utilises par la direction, dont certains ne partagent JAMAIS un
frn_code commun dans nos PO actuels (aucune preuve data-driven possible) --
ex. POLLYDA / DIAMOND TRACK / GUANGWEI : POLLYDA n'apparait sur aucun PO avec
le frn_code de GUANGWEI (00001220), donc l'algorithme frn_code seul ne peut
PAS le detecter. D'ou ALIAS_CONNUS ci-dessous, fusionne AVANT le Union-Find
par frn_code (les deux mecanismes se completent, ne se remplacent pas).

Usage : python -m src.scripts.etl.enrich_ca
"""
from __future__ import annotations

import logging

import pandas as pd
from sqlalchemy import create_engine, text

from src.utils.config_manager import Config

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

SCHEMAS = {
    "GDD": "TARRERIAS_GENERALE_DE_DECOUPAGE_Achat",
    "SE": "TARRERIAS_SE_TARRERIAS_BONJEAN_Achat",
    "Cie": "TARRERIAS_TARRERIAS_BONJEAN_ET_CIE_Achat",
}

# Nombre minimum de PO distincts requis pour retenir un lien (nom, societe, frn_code)
# -- voir garde-fou anti-faux-positif dans le docstring module.
MIN_PO_SUPPORT = 2

# Synonymes de fournisseur connus du metier (Andrea, questionnaire de passation
# 21/07) mais indetectables par le seul frn_code faute de PO partage en donnees
# actuelles. HUGUESUN et VICO n'apparaissent pour l'instant dans aucun PO
# (verifie le 23/07) -- gardes ici pour que la fusion s'applique automatiquement
# des qu'ils apparaitront dans un futur import.
ALIAS_CONNUS: list[list[str]] = [
    ["POLLYDA", "DIAMOND TRACK", "GUANGWEI"],
    ["HUGUESUN", "SMART IRON", "JIT GLOBAL"],
    ["HIAMEA", "AOYAM"],
    ["VICO", "MINGHAO"],
]


def _group_by_frn_code(four2codes: dict[str, set], alias_groups: list[list[str]] | None = None) -> list[dict]:
    """
    Regroupe les noms fournisseur (texte) par composante connexe sur le graphe
    biparti nom <-> (societe, frn_code).

    Junior Tip : un simple dict {nom: code} ne suffit pas -- un nom peut avoir
    plusieurs codes (multi-societes) ET un code peut etre partage par plusieurs
    noms (doublon de saisie, ex. GUANGWEI / DIAMOND TRACK = frn 00001220). Un
    Union-Find sur "nom" et "(soc, code)" comme noeuds fusionne transitivement
    tout ce qui est relie, meme sur plusieurs sauts.

    Args:
        four2codes: {nom_fournisseur: {(societe, frn_code), ...}}
    Returns:
        Liste de groupes {"noms": {...}, "codes": {(soc, code), ...}}.
    """
    parent: dict = {}

    def find(x):
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    for nom, codes in four2codes.items():
        find(nom)
        for code in codes:
            union(nom, code)

    # Alias connus (source humaine, cf. docstring module) : fusionnes en plus des
    # liens frn_code, pour les cas ou 2 noms ne partagent jamais de PO commun.
    for cluster in (alias_groups or []):
        for a, b in zip(cluster, cluster[1:]):
            union(a, b)

    groups: dict = {}
    for nom, codes in four2codes.items():
        root = find(nom)
        g = groups.setdefault(root, {"noms": set(), "codes": set()})
        g["noms"].add(nom)
        g["codes"] |= codes

    return list(groups.values())


def run() -> int:
    """
    Calcule le CA 3 ans par fournisseur et l'upsert dans achat.fournisseur_ca.

    Junior Tip : on derive le mapping nom->code depuis NOS commandes (join PO),
    puis on additionne le CA par code cote Sylob. Un meme nom peut pointer plusieurs
    codes (selon societe) : on somme alors sur l'ensemble de ses codes.

    Returns:
        Nombre de fournisseurs upsertes.
    """
    pg = create_engine(Config.get_pg_url())
    sy = create_engine(Config.get_sylob_url())

    with pg.connect() as c:
        cmd = c.execute(text(
            "SELECT DISTINCT po_number, fournisseur FROM achat.commande "
            "WHERE po_number IS NOT NULL AND fournisseur IS NOT NULL"
        )).fetchall()
    pad2four = {str(po).strip().zfill(8): four.strip() for po, four in cmd}
    pads = list(pad2four.keys())
    logger.info("[INFO] %d PO pour deriver le mapping nom->frn", len(pads))

    # 1. comptage brut des liens (nom, societe, frn_code) -> nb de PO distincts
    edge_po_count: dict[tuple, set] = {}
    with sy.connect() as c:
        for soc, schema in SCHEMAS.items():
            for numero, frn in c.execute(text(
                f'SELECT commande_numero_de_la_commande, frn_code_fournisseur '
                f'FROM "{schema}".vue_commande_achat WHERE commande_numero_de_la_commande = ANY(:p)'
            ), {"p": pads}).fetchall():
                four = pad2four.get(str(numero).strip())
                if four and frn:
                    key = (four, soc, str(frn).strip())
                    edge_po_count.setdefault(key, set()).add(str(numero).strip())

    # 2. mapping (fournisseur -> set de (societe, frn_code)). Le filtre MIN_PO_SUPPORT
    # ne s'applique qu'en cas d'ambiguite (plusieurs codes candidats pour un meme nom) --
    # un nom avec un seul code candidat est conserve quel que soit son nb de PO
    # (cf. garde-fou module : POLLYDA et consorts ne doivent pas disparaitre).
    edges_by_four: dict[str, list] = {}
    for (four, soc, frn), pos in edge_po_count.items():
        edges_by_four.setdefault(four, []).append((soc, frn, len(pos)))

    four2codes: dict[str, set] = {}
    rejetes = []
    for four, edges in edges_by_four.items():
        if len(edges) == 1:
            soc, frn, _n = edges[0]
            four2codes.setdefault(four, set()).add((soc, frn))
            continue
        retenus = [(soc, frn) for soc, frn, n in edges if n >= MIN_PO_SUPPORT]
        if not retenus:
            # Aucun candidat robuste (tous en dessous du seuil) : on garde le mieux
            # corrobore plutot que de perdre le fournisseur, et on le signale.
            soc, frn, n = max(edges, key=lambda e: e[2])
            retenus = [(soc, frn)]
            logger.warning("[ATTENTION] %s : tous les codes < %d PO, code le mieux corrobore retenu (%s/%s, %d PO)",
                           four, MIN_PO_SUPPORT, soc, frn, n)
        four2codes[four] = set(retenus)
        for soc, frn, n in edges:
            if (soc, frn) not in retenus:
                rejetes.append((four, soc, frn, n))
    if rejetes:
        logger.info("[INFO] %d lien(s) nom<->frn_code rejete(s) (ambigu, < %d PO, bruit probable) : %s",
                    len(rejetes), MIN_PO_SUPPORT,
                    "; ".join(f"{f} ({s}/{c}, {n} PO)" for f, s, c, n in rejetes))

    # 3. CA par (societe, frn_code) sur 3 ans
    ca_by_code: dict[tuple, list] = {}
    with sy.connect() as c:
        for soc, schema in SCHEMAS.items():
            codes = {fc for s2, fc in {c2 for v in four2codes.values() for c2 in v} if s2 == soc}
            if not codes:
                continue
            for frn, ca, nb in c.execute(text(
                f'''SELECT frn_code_fournisseur, SUM(commande_total_ht), COUNT(*)
                    FROM "{schema}".vue_commande_achat
                    WHERE frn_code_fournisseur = ANY(:c)
                      AND commande_creee_le >= (CURRENT_DATE - INTERVAL '3 years')
                    GROUP BY frn_code_fournisseur'''
            ), {"c": list(codes)}).fetchall():
                ca_by_code[(soc, str(frn).strip())] = [float(ca or 0), int(nb or 0)]

    groups = _group_by_frn_code(four2codes, ALIAS_CONNUS)

    rows = []
    for g in groups:
        codes = g["codes"]
        ca = sum(ca_by_code.get(k, [0, 0])[0] for k in codes)
        nb = sum(ca_by_code.get(k, [0, 0])[1] for k in codes)
        noms = sorted(g["noms"])
        rows.append({
            "fournisseur": " / ".join(noms),  # doublons fusionnes (meme frn_code) affiches ensemble
            "frn_codes": ", ".join(sorted(fc for _, fc in codes)),
            "ca_3ans": round(ca, 2), "nb_commandes": nb,
        })

    if not rows:
        logger.warning("[ATTENTION] Aucun CA calcule -- rien a charger.")
        return 0

    n_fusionnes = sum(1 for g in groups if len(g["noms"]) > 1)
    if n_fusionnes:
        logger.info("[INFO] %d groupe(s) fusionne(s) (doublon de nom sur un meme frn_code) : %s",
                    n_fusionnes,
                    "; ".join(" / ".join(sorted(g["noms"])) for g in groups if len(g["noms"]) > 1))

    df = pd.DataFrame(rows)
    # Full-refresh : le grain a change (nom texte -> groupe frn_code), un simple
    # UPSERT sur l'ancienne cle "fournisseur" laisserait les anciennes lignes
    # doublonnees en base (ex. GUANGWEI et DIAMOND TRACK separement).
    with pg.begin() as c:
        c.execute(text("TRUNCATE TABLE achat.fournisseur_ca;"))
        df.to_sql("fournisseur_ca", c, schema="achat", if_exists="append", index=False, method="multi")
    logger.info("[SUCCÈS] achat.fournisseur_ca enrichi (full-refresh) : %d fournisseurs", len(rows))
    return len(rows)


if __name__ == "__main__":
    run()
