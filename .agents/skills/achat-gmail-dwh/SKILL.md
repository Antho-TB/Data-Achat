---
name: achat:gmail-dwh
description: >
  Pipeline Gmail → DWH pour le service Achats TB Groupe. Utilise ce skill pour lancer
  ou configurer l'extraction automatique des mails fournisseurs depuis Gmail, l'analyse
  structurée des données (PO, prix, ETD, BL), et l'écriture dans achat.commande (PostgreSQL Azure).
  Déclencher avec : "extraire les mails fournisseurs", "lancer le pipeline Achats",
  "alimenter la base depuis Gmail", "configurer la tâche planifiée Achats".
---

# Pipeline Gmail → DWH Achats — Orchestration (v2, alignée poste Marlène 2026-06-29)

## Vue d'ensemble

```
Gmail (Marlène, connecteur Cowork)
  → search_threads (mots-clés / label Achats/Fournisseurs)
  → get_thread (corps)
  → achatanalyser-mail (extraction structurée)
  → Script Python local (Windows + VPN actif)
  → UPSERT achat.commande (PostgreSQL Azure)
```

## ⚠️ Contraintes critiques (à lire avant tout run)

1. **Réseau** : le DWH Azure n'est accessible que via VPN Stormshield. Le bash Cowork
   (Linux sandbox) ne peut PAS l'atteindre. **Toujours exécuter le script via PowerShell
   local** (`mcp__Windows-MCP__PowerShell`).
2. **Auth poste Marlène** : `KEY_VAULT_NAME` est VIDE → **pas de Key Vault / pas d'az login**.
   Les credentials viennent de `config/.env` (`PG_USER=platform_team`). On réutilise la
   classe `Config` du projet (`src/utils/config_manager`), jamais un client Key Vault.
3. **Droits** : l'écriture dans `achat.commande` exige le GRANT posé le 29/06
   (`sql/20260629_grant_platform_team_commande.sql`). Sans lui → `permission denied`.

## Étape 1 — Lire les mails Gmail (connecteur Cowork)

Connecteur Gmail connecté (Cowork > Paramètres > Connecteurs).

```
search_threads, ex. :
- query: "newer_than:1d (from:factory OR from:supplier OR label:Achats/Fournisseurs)"
- ou expéditeurs connus : TB China, transitaire, DEKRA
get_thread → corps de chaque fil
```

## Étape 2 — Analyser chaque mail

Appliquer le skill `achatanalyser-mail` : type (commande/suivi/livraison/prix), champs
structurés, incohérences vs base. Agréger en liste JSON.

## Étape 3 — Écrire dans le DWH (pattern A : zone découplée)

> ⚠️ **Ne JAMAIS écrire les données d'expédition Gmail dans `achat.commande`.** Cette table
> est full-refresh (TRUNCATE+INSERT) par l'ETL Excel — et sa source de base migre vers le
> DWH Sylob V25. Tout INSERT/UPDATE direct y serait effacé au prochain run. Décision 30/06.

Découpage des données extraites des mails :

| Donnée | Niveau | Cible | Mécanisme |
|--------|--------|-------|-----------|
| `n_conteneur`, `n_bl`, `etd_reel`, `eta`, `transitaire`, `n_facture`, `lieu_livraison` | Expédition (BL) | **`achat.ot_transport`** (PK `n_conteneur`) | UPSERT `ON CONFLICT (n_conteneur)` |
| `etd_confirme` | Ordre (corps de mail, niveau PO) | `achat.commande` | `apply_etd_eta.py` (UPDATE par PO) |

Les vues `v_previsionnel` / `v_retard_article` fusionnent les deux (`COALESCE(ot.etd_reel, c.etd_reel, c.etd_confirme)` — BL prioritaire), donc la donnée Gmail pilote le prévisionnel sans toucher la table de base.

Script à exécuter via PowerShell local. **Colonnes alignées sur le DDL réel d'`achat.ot_transport`**
(provenance via `source_fichier`, PAS `source` qui n'existe pas) :

```python
# achat_gmail_ot.py — upsert ot_transport (zone expédition), credentials via Config
import json, sys, logging
import pandas as pd
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL
from src.utils.config_manager import Config  # standard projet — gère .env + URL.create

logging.basicConfig(level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s")
logger = logging.getLogger(__name__)

cfg = Config()  # KEY_VAULT_NAME vide => credentials depuis .env (platform_team)
engine = create_engine(URL.create(
    drivername="postgresql+psycopg2",
    username=cfg.pg_user, password=cfg.pg_password,
    host=cfg.pg_host, port=cfg.pg_port, database=cfg.pg_db,
    query={"sslmode": cfg.pg_sslmode},
))

data = json.loads(sys.argv[1])           # [{"n_conteneur": "...", "n_bl": "...", "etd_reel": "...", "eta": "...", ...}]
df = pd.DataFrame(data)

# UPSERT par n_conteneur — COALESCE pour ne pas écraser un champ existant avec un NULL
with engine.begin() as conn:
    for _, row in df.iterrows():
        if not str(row.get("n_conteneur", "")).strip():
            logger.warning("Ligne ignorée (n_conteneur manquant) : %s", row.to_dict())
            continue
        conn.execute(text("""
            INSERT INTO achat.ot_transport
                (n_conteneur, n_bl, etd_reel, eta, transitaire, n_facture,
                 lieu_livraison, source_fichier, charge_le)
            VALUES
                (:n_conteneur, :n_bl, :etd_reel, :eta, :transitaire, :n_facture,
                 :lieu_livraison, 'gmail', NOW())
            ON CONFLICT (n_conteneur) DO UPDATE SET
                n_bl           = COALESCE(EXCLUDED.n_bl,           achat.ot_transport.n_bl),
                etd_reel       = COALESCE(EXCLUDED.etd_reel,       achat.ot_transport.etd_reel),
                eta            = COALESCE(EXCLUDED.eta,            achat.ot_transport.eta),
                transitaire    = COALESCE(EXCLUDED.transitaire,    achat.ot_transport.transitaire),
                n_facture      = COALESCE(EXCLUDED.n_facture,      achat.ot_transport.n_facture),
                lieu_livraison = COALESCE(EXCLUDED.lieu_livraison, achat.ot_transport.lieu_livraison),
                source_fichier = 'gmail',
                charge_le      = NOW()
        """), {k: row.get(k) for k in
               ("n_conteneur","n_bl","etd_reel","eta","transitaire","n_facture","lieu_livraison")})

logger.info("[SUCCES] %d conteneur(s) upsert dans achat.ot_transport", len(df))
```

Pour l'`etd_confirme` niveau PO (corps de mail, sans conteneur) :
```powershell
python -m src.scripts.gmail.apply_etd_eta --data '<json [{"po_number":"...","etd_confirme":"..."}]>'
```

> Annotations métier (raisons de retard, notes) → table `achat.commande_annotation`
> (déjà ouverte à platform_team), pas dans `achat.commande`.

### Chaîne outillée (scripts du repo — à privilégier au snippet ci-dessus)

Le snippet est la référence pédagogique ; en pratique on utilise les scripts versionnés :

```powershell
# 1) Parser les BL PDF (data/PJ) -> JSON expédition (texte + OCR fallback)
python -m src.scripts.gmail.parse_bl --folder data/PJ --out data/PJ/_parsed.json
# 2) Upsert dans achat.ot_transport (--dry-run d'abord, puis sans pour COMMIT)
python -m src.scripts.gmail.load_ot_gmail --file data/PJ/_parsed.json --dry-run
python -m src.scripts.gmail.load_ot_gmail --file data/PJ/_parsed.json
# 3) etd_confirme niveau PO (corps de mail) -> achat.commande
python -m src.scripts.gmail.apply_etd_eta --data '<json [{"po_number":"...","etd_confirme":"..."}]>'
```
OCR (PDF scannés) : nécessite **tesseract-ocr (+ fra)** et **poppler** installés sur le poste.

## Étape 4 — Tâche planifiée

Via le skill `schedule` : `0 8-18/2 * * 1-5` (toutes les 2h, heures ouvrées).
Prérequis : VPN actif + Cowork ouvert sur le poste de Marlène.

## Prérequis installation

1. Connecteur **Gmail** connecté dans Cowork (compte Marlène).
2. **VPN Stormshield** actif.
3. **Python 3.11** + packages : `sqlalchemy psycopg2-binary pandas` (Key Vault inutile ici).
4. `config/.env` renseigné (`platform_team`, `KEY_VAULT_NAME` vide).
5. GRANT `platform_team` sur `achat.commande` appliqué (sql/20260629_grant_platform_team_commande.sql).
