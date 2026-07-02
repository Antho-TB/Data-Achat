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
Montant en devise commande (USD pour les imports). Lecture seule Sylob ; UPSERT cote achat.

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

    # 1. mapping (fournisseur -> set de (societe, frn_code)) via le join PO
    four2codes: dict[str, set] = {}
    # 2. CA par (societe, frn_code) sur 3 ans
    ca_by_code: dict[tuple, list] = {}
    with sy.connect() as c:
        for soc, schema in SCHEMAS.items():
            # mapping
            for numero, frn in c.execute(text(
                f'SELECT commande_numero_de_la_commande, frn_code_fournisseur '
                f'FROM "{schema}".vue_commande_achat WHERE commande_numero_de_la_commande = ANY(:p)'
            ), {"p": pads}).fetchall():
                four = pad2four.get(str(numero).strip())
                if four and frn:
                    four2codes.setdefault(four, set()).add((soc, str(frn).strip()))
            # CA 3 ans pour les codes concernes
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

    rows = []
    for four, codes in four2codes.items():
        ca = sum(ca_by_code.get(k, [0, 0])[0] for k in codes)
        nb = sum(ca_by_code.get(k, [0, 0])[1] for k in codes)
        rows.append({
            "fournisseur": four,
            "frn_codes": ", ".join(sorted(fc for _, fc in codes)),
            "ca_3ans": round(ca, 2), "nb_commandes": nb,
        })

    if not rows:
        logger.warning("[ATTENTION] Aucun CA calcule -- rien a charger.")
        return 0

    df = pd.DataFrame(rows)
    with pg.begin() as c:
        df.to_sql("_tmp_ca", c, schema="achat", if_exists="replace", index=False, method="multi")
        c.execute(text("""
            INSERT INTO achat.fournisseur_ca (fournisseur, frn_codes, ca_3ans, nb_commandes)
            SELECT fournisseur, frn_codes,
                   NULLIF(ca_3ans::text,'')::numeric, NULLIF(nb_commandes::text,'')::int
            FROM achat._tmp_ca
            ON CONFLICT (fournisseur) DO UPDATE SET
                frn_codes = EXCLUDED.frn_codes, ca_3ans = EXCLUDED.ca_3ans,
                nb_commandes = EXCLUDED.nb_commandes, charge_le = now();
        """))
        c.execute(text("DROP TABLE IF EXISTS achat._tmp_ca;"))
    logger.info("[SUCCÈS] achat.fournisseur_ca enrichi : %d fournisseurs", len(rows))
    return len(rows)


if __name__ == "__main__":
    run()
