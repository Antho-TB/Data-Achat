# -*- coding: utf-8 -*-
"""
[ETL]
=============================================================================
ENRICHISSEMENT ACOMPTE - SOURCE IMPORT 2026
=============================================================================

Enrichissement de achat.acompte depuis le DWH Sylob (tarrerias_production_dwh).

Recupere l'acompte verse par commande dans les 3 societes (GDD, SE, Cie) et
l'ecrit dans achat.acompte (PostgreSQL Azure). Besoin metier : les fournisseurs
reclament parfois le total en oubliant l'acompte deja verse.

Cle de jointure : Sylob `commande_numero_de_la_commande` (8 zero-padde) = `po_number`.
Chaque PO appartient a une seule societe. Montants en devise commande (USD pour
les imports). Lecture seule cote Sylob ; UPSERT idempotent cote achat.acompte.

Usage : python -m src.scripts.etl.enrich_acompte
"""
from __future__ import annotations

import logging

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
    Lit les acomptes Sylob pour les PO presents dans achat.commande et les upsert.

    Junior Tip : on ne tire que les commandes qui nous interessent (PO de l'IMPORT),
    via `numero = ANY(:pos)`, plutot que de balayer les 130k commandes Sylob -- la
    liste de PO joue le role de filtre cote serveur (index-friendly).

    Returns:
        Nombre de lignes acompte upsertees.
    """
    pg = create_engine(Config.get_pg_url())
    sy = create_engine(Config.get_sylob_url())

    with pg.connect() as c:
        pos = [str(r[0]).strip() for r in c.execute(
            text("SELECT DISTINCT po_number FROM achat.commande WHERE po_number IS NOT NULL")
        ).fetchall()]
    pos_pad = {p.zfill(8): p for p in pos}  # padded -> po d'origine
    logger.info("[INFO] %d PO a enrichir", len(pos))

    rows: list[dict] = []
    with sy.connect() as c:
        for soc, schema in SCHEMAS.items():
            res = c.execute(text(f'''
                SELECT commande_numero_de_la_commande        AS numero,
                       commande_montant_de_l_acompte         AS montant,
                       commande_pourcentage_d_acompte        AS pct,
                       commande_net_a_payer                  AS net,
                       commande_total_ht                     AS total_ht
                FROM "{schema}".vue_commande_achat
                WHERE commande_numero_de_la_commande = ANY(:pads)
            '''), {"pads": list(pos_pad.keys())}).mappings().all()
            for r in res:
                po = pos_pad.get(str(r["numero"]).strip())
                if not po:
                    continue
                rows.append({
                    "po_number": po, "societe": soc,
                    "montant_acompte": r["montant"], "pourcentage_acompte": r["pct"],
                    "net_a_payer": r["net"], "total_ht": r["total_ht"],
                })
            logger.info("[INFO] %s : %d commandes appariees", soc, len(res))

    if not rows:
        logger.warning("[ATTENTION] Aucun acompte apparie -- rien a charger.")
        return 0

    # Un meme numero peut exister dans 2 societes (numerotation independante) ->
    # collision. On garde, par po, la commande la plus "reelle" : acompte renseigne
    # d'abord, sinon total_ht le plus eleve.
    best: dict[str, dict] = {}
    for r in rows:
        k = r["po_number"]
        score = (1 if (r["montant_acompte"] or 0) else 0, float(r["total_ht"] or 0))
        if k not in best or score > best[k]["_score"]:
            best[k] = {**r, "_score": score}
    rows = [{kk: vv for kk, vv in r.items() if kk != "_score"} for r in best.values()]
    logger.info("[INFO] %d PO uniques apres dedoublonnage inter-societes", len(rows))

    # Staging dans le schema achat (le compte n'a pas le droit CREATE TEMP en prod).
    import pandas as pd
    df = pd.DataFrame(rows)
    with pg.begin() as c:
        df.to_sql("_tmp_acompte", c, schema="achat", if_exists="replace", index=False, method="multi")
        c.execute(text("""
            INSERT INTO achat.acompte
                (po_number, societe, montant_acompte, pourcentage_acompte, net_a_payer, total_ht)
            SELECT po_number, societe,
                   NULLIF(montant_acompte::text,'')::numeric, NULLIF(pourcentage_acompte::text,'')::numeric,
                   NULLIF(net_a_payer::text,'')::numeric, NULLIF(total_ht::text,'')::numeric
            FROM achat._tmp_acompte
            ON CONFLICT (po_number) DO UPDATE SET
                societe = EXCLUDED.societe,
                montant_acompte = EXCLUDED.montant_acompte,
                pourcentage_acompte = EXCLUDED.pourcentage_acompte,
                net_a_payer = EXCLUDED.net_a_payer,
                total_ht = EXCLUDED.total_ht,
                charge_le = now();
        """))
        c.execute(text("DROP TABLE IF EXISTS achat._tmp_acompte;"))
    logger.info("[SUCCÈS] achat.acompte enrichi : %d lignes", len(rows))
    return len(rows)


if __name__ == "__main__":
    run()
