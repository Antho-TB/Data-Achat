# -*- coding: utf-8 -*-
"""
[ETL]
=============================================================================
GENERATION docs/achat_schema.yaml -- schema machine-readable achat.*
=============================================================================
Introspecte information_schema (colonnes, PK/UNIQUE) sur le schema achat de
dtpf_sylob_prod et fusionne avec les descriptions metier deja ecrites a la
main dans docs/modele_semantique.md (role, grain, source de captation,
presence dans Sylob V25). Objectif (demande Antho 02/07) : une seule source
de verite versionnee, reutilisable par un skill (evite de re-derouler
l'investigation Sylob/FUSEAU a chaque session).

Junior Tip : l'introspection (colonnes/types/PK) est TOUJOURS a jour car elle
lit la structure reelle de la base -- mais le sens metier (role, source,
Sylob ?) ne peut pas se deviner depuis information_schema, il vient du
dictionnaire ecrit a la main (TABLE_META ci-dessous, a maintenir en meme
temps que docs/modele_semantique.md).

Usage (VPN actif, poste) :
    python -m src.scripts.etl.generate_schema_yaml
"""
from __future__ import annotations

import logging
import sys
from datetime import date, datetime, timezone

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(name)s -- %(message)s")
logger = logging.getLogger("generate_schema_yaml")

# Descriptions metier -- miroir de docs/modele_semantique.md ## Dictionnaire des
# tables. A tenir a jour manuellement en meme temps que ce document (source de
# verite humaine ; ce script ne fait qu'introspecter la structure SQL).
TABLE_META: dict[str, dict] = {
    "commande": {
        "role": "Suivi commandes import (coeur)",
        "grain": "ligne article x commande",
        "source_captation": "IMPORT 2025.xlsx (copie figee poste Antho)",
        "sylob": "partiel -- oui : Achat.f_commandeachat/f_lignecommandeachat/vue_commande_achat_detail (societe TARRERIAS_SE_TARRERIAS_BONJEAN, V25)",
    },
    "produit": {
        "role": "Referentiel produit enrichi",
        "grain": "article",
        "source_captation": "Matrice TB Import.xlsx + pull direct Sylob V25 (enrich_dimensions.py, packaging/dimensions)",
        "sylob": "oui (Article.af_article, 149 colonnes natives)",
    },
    "acompte": {
        "role": "Acompte verse par PO",
        "grain": "PO",
        "source_captation": "IMPORT (col Acompte)",
        "sylob": "non -- aucune table acompte dans Finances/Achat (verifie V25) ; conditions de reglement existent (a_conditionreglement) mais pas le montant verse",
    },
    "fournisseur_ca": {
        "role": "CA cumule 3 ans",
        "grain": "fournisseur",
        "source_captation": "Sylob (vue_commande_achat)",
        "sylob": "oui (derivable de vue_commande_achat)",
    },
    "article_nomenclature": {
        "role": "Nomenclature composant+packaging+gamme+HS",
        "grain": "article",
        "source_captation": "Matrice TB Import.xlsx",
        "sylob": "partiel, largement oui -- voir docs/20260702_audit_champs_sylob_v25.md",
    },
    "article_nomenclature_composant": {
        "role": "Detail composant (1..8) pour articles multi-composant (coffrets)",
        "grain": "article x position",
        "source_captation": "Matrice TB Import / Lot Multiples produits (copie figee mars 2026)",
        "sylob": "non (custom TB)",
    },
    "ot_transport": {
        "role": "Suivi expedition maritime",
        "grain": "conteneur",
        "source_captation": "SUIVI MARITIME (transitaire, gsheet live) ; bootstrap depuis achat.commande si absent",
        "sylob": "non (aucun concept transport/conteneur dans les schemas audites)",
    },
    "artwork": {
        "role": "Artwork par commande",
        "grain": "po x article",
        "source_captation": "IMPORT",
        "sylob": "non (pas de concept design/artwork ERP)",
    },
    "artwork_statut": {
        "role": "Statut validation design",
        "grain": "article",
        "source_captation": "Suivi artworks (Clarisse, gsheet)",
        "sylob": "non",
    },
    "qualite": {
        "role": "Qualite par commande",
        "grain": "po x article",
        "source_captation": "IMPORT (MAT/SP/conformite)",
        "sylob": "partiel-oui : Qualite.f_controlequalitereception/vue_controle_qualite_reception couvre le controle reception ; af_article.sup_rapport_dinspection/sup_certificat_matiere = flags Oui/Non (pas de lien fichier)",
    },
    "qualite_doc": {
        "role": "Index rapports (lien FAIL vers fichier)",
        "grain": "fichier rapport",
        "source_captation": "Drive/serveur ANALYSES ET INSPECTIONS",
        "sylob": "non (Sylob n'a que le flag Oui/Non, pas le lien vers le PDF)",
    },
    "qualite_analyse": {
        "role": "Mesures labo (chrome/durete/conformite)",
        "grain": "fichier rapport",
        "source_captation": "rapports SPECTRO (PDF)",
        "sylob": "non (mesures labo detaillees absentes de Sylob)",
    },
    "qualite_suivi": {
        "role": "Suivi analyses labo (blocs A+D)",
        "grain": "id",
        "source_captation": "Suivi analyses (Gmail/Drive, Andrea)",
        "sylob": "non",
    },
    "qualite_facturation": {
        "role": "Facturation qualite (bloc E)",
        "grain": "id",
        "source_captation": "Suivi analyses (Gmail/Drive, Andrea)",
        "sylob": "non",
    },
    "commande_annotation": {
        "role": "Notes metier (survit au full-refresh de commande)",
        "grain": "po x article",
        "source_captation": "saisie FUSEAU",
        "sylob": "non (custom FUSEAU)",
    },
    "mif_suivi": {
        "role": "Bilan Made In France (lames/couteaux par lot PP x coloris)",
        "grain": "gamme x stade x lot_pp x coloris",
        "source_captation": "IMPORT 2026 / POINT MIF (copie figee mars 2026)",
        "sylob": "non",
    },
    "article_cycle_vie": {
        "role": "Cycle de vie articles Carrefour (arret/en cours)",
        "grain": "article",
        "source_captation": "IMPORT 2026 / STOP REF CARREFOUR (copie figee mars 2026)",
        "sylob": "non",
    },
    "v_previsionnel": {
        "role": "Vue de lecture -- previsionnel merge (BL/maritime prioritaire, COALESCE)",
        "grain": "derive de commande + ot_transport",
        "source_captation": "vue SQL (pas de captation propre)",
        "sylob": "n/a (vue)",
    },
    "v_retard_article": {
        "role": "Vue de lecture -- retard par article",
        "grain": "derive de commande",
        "source_captation": "vue SQL (pas de captation propre)",
        "sylob": "n/a (vue)",
    },
    "v_artwork": {
        "role": "Vue de lecture -- statut artwork consolide",
        "grain": "derive de artwork_statut",
        "source_captation": "vue SQL (pas de captation propre)",
        "sylob": "n/a (vue)",
    },
    "v_qualite_fournisseur": {
        "role": "Vue de lecture -- qualite par fournisseur",
        "grain": "derive de qualite_doc",
        "source_captation": "vue SQL (pas de captation propre)",
        "sylob": "n/a (vue)",
    },
    "v_retard_expedition": {
        "role": "Vue de lecture -- retard fige par expedition (grain ligne PO x article)",
        "grain": "derive de commande + ot_transport",
        "source_captation": "vue SQL (pas de captation propre)",
        "sylob": "n/a (vue)",
    },
    "v_retard_fournisseur": {
        "role": "Vue de lecture -- retard moyen fige par fournisseur (12 mois glissants)",
        "grain": "derive de v_retard_expedition",
        "source_captation": "vue SQL (pas de captation propre)",
        "sylob": "n/a (vue)",
    },
    # 4 tables evenements metier email-first (creees 22/07,
    # sql/20260722_tables_evenements_metier.sql), grain evenement,
    # idempotence via cle_idempotence -- remplacent le fourre-tout
    # commande_annotation pour les threads Gmail non lies au transport.
    "qualite_decision": {
        "role": "Decision conforme/non-conforme (email-first, Eric T)",
        "grain": "evenement",
        "source_captation": "threads Gmail (corps)",
        "sylob": "non (email-first ; FNC formel Sylob a reconcilier)",
    },
    "transport_evenement": {
        "role": "Retards / imprevus / changements ETD-ETA-livraison",
        "grain": "evenement",
        "source_captation": "threads Gmail + transitaire",
        "sylob": "non (transport absent de Sylob)",
    },
    "commerce_decision": {
        "role": "Arbitrages commerce (prix client, go/no-go, priorite, promo)",
        "grain": "evenement",
        "source_captation": "threads Gmail (Eric/David)",
        "sylob": "non (informel commerce)",
    },
    "design_evenement": {
        "role": "Validations design (boite, artwork, marquage, pantone)",
        "grain": "evenement",
        "source_captation": "threads Gmail (Clarisse)",
        "sylob": "non (design absent de Sylob)",
    },
}

# Colonnes dont le sens n'est pas evident depuis leur seul nom -- documentees
# individuellement (traçabilite, bugs corriges, ambiguites levees le 02/07).
COLUMN_NOTES: dict[str, dict[str, str]] = {
    "commande": {
        "nom_navire": "Nom du navire (colonne Excel 'Transport'). Fix 02/07 : anciennement mal-mappe dans transitaire.",
        "transitaire": "Transporteur reel (colonne Excel 'Transitaire', ex. QUALITAIRSEA/SEALOGIS). Distinct de nom_navire.",
        "prix_reference": "Colonne Excel 'Prix / reference', distincte de prix_unitaire (PU = prix commande).",
        "total_prix_facture": "Colonne Excel 'Total prix sur facture', distincte de total_prix (= prix commande).",
        "pcb_ligne": "PCB au grain ligne de commande (colonne Excel 'PCB') -- distinct de produit.pcb (referentiel article).",
    },
    "produit": {
        "source_dimensions": "'sylob_v25' si au moins un champ packaging/dimension vient du pull Sylob V25 (enrich_dimensions.py), NULL sinon (Matrice Excel ou jamais renseigne).",
        "sylob_dimensions_synced_at": "Horodatage dedie packaging/dimensions -- distinct de sylob_synced_at (pose par enrich_from_sylob.py pour le bloc prix/delai) pour ne pas ecraser le marqueur de l'autre job.",
        "sylob_synced_at": "Horodatage du dernier sync Sylob pour le bloc prix/delai_reappro (enrich_from_sylob.py).",
    },
}


def introspect_columns(conn) -> dict[str, list[dict]]:
    from sqlalchemy import text
    rows = conn.execute(text("""
        SELECT table_name, column_name, data_type, is_nullable, column_default,
               character_maximum_length, numeric_precision, numeric_scale
        FROM information_schema.columns
        WHERE table_schema = 'achat'
        ORDER BY table_name, ordinal_position
    """)).fetchall()
    out: dict[str, list[dict]] = {}
    for r in rows:
        out.setdefault(r[0], []).append({
            "name": r[1],
            "type": r[2],
            "nullable": r[3] == "YES",
            "default": r[4],
        })
    return out


def introspect_keys(conn) -> dict[str, dict[str, list[str]]]:
    """Retourne {table: {'PRIMARY KEY': [...], 'UNIQUE': [...]}} par table."""
    from sqlalchemy import text
    rows = conn.execute(text("""
        SELECT tc.table_name, tc.constraint_type, kcu.column_name
        FROM information_schema.table_constraints tc
        JOIN information_schema.key_column_usage kcu
          ON tc.constraint_name = kcu.constraint_name AND tc.table_schema = kcu.table_schema
        WHERE tc.table_schema = 'achat' AND tc.constraint_type IN ('PRIMARY KEY', 'UNIQUE')
        ORDER BY tc.table_name, tc.constraint_type, kcu.ordinal_position
    """)).fetchall()
    out: dict[str, dict[str, list[str]]] = {}
    for table, ctype, col in rows:
        out.setdefault(table, {}).setdefault(ctype, []).append(col)
    return out


def build_schema(conn) -> dict:
    cols_by_table = introspect_columns(conn)
    keys_by_table = introspect_keys(conn)

    tables = {}
    for table_name, cols in sorted(cols_by_table.items()):
        meta = TABLE_META.get(table_name, {})
        if not meta:
            logger.warning("[ATTENTION] Table achat.%s sans description dans TABLE_META "
                            "-- ajouter une entree (cf. docs/modele_semantique.md).", table_name)
        notes = COLUMN_NOTES.get(table_name, {})
        columns_out = []
        for c in cols:
            entry = dict(c)
            if c["name"] in notes:
                entry["note"] = notes[c["name"]]
            columns_out.append(entry)

        tables[table_name] = {
            "role": meta.get("role", "(a documenter)"),
            "grain": meta.get("grain", "(a documenter)"),
            "source_captation": meta.get("source_captation", "(a documenter)"),
            "existe_dans_sylob": meta.get("sylob", "(a documenter)"),
            "cles": keys_by_table.get(table_name, {}),
            "colonnes": columns_out,
        }

    return {
        "genere_le": datetime.now(timezone.utc).isoformat(),
        "schema_postgres": "achat",
        "base": "dtpf_sylob_prod",
        "avertissement": (
            "Structure SQL auto-introspectee (toujours fiable) ; role/source/Sylob "
            "issus de TABLE_META (maintenu a la main, cf. docs/modele_semantique.md). "
            "FUSEAU est un POC : ces tables ont vocation a etre reintegrees dans Sylob."
        ),
        "tables": tables,
    }


def run(output_path: str) -> None:
    sys.path.insert(0, ".")
    from src.utils.config_manager import Config
    from sqlalchemy import create_engine
    import yaml

    engine = create_engine(Config.get_pg_url())
    with engine.connect() as conn:
        schema = build_schema(conn)

    with open(output_path, "w", encoding="utf-8") as f:
        yaml.safe_dump(schema, f, allow_unicode=True, sort_keys=False, default_flow_style=False)

    n_tables = len(schema["tables"])
    n_cols = sum(len(t["colonnes"]) for t in schema["tables"].values())
    logger.info("[SUCCÈS] %s généré : %d tables, %d colonnes.", output_path, n_tables, n_cols)


def main() -> int:
    run("docs/achat_schema.yaml")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
