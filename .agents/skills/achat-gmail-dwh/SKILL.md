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

## Étape 3 — Écrire dans le DWH (DDL réel + auth .env)

Script à exécuter via PowerShell local. **Colonnes alignées sur le DDL réel** :
`etd_confirme` / `etd_reel` / `eta` (PAS `date_etd`), pas de colonne `type_mail`.

```python
# achat_gmail_load.py — v2, lit les credentials depuis config/.env via Config
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

data = json.loads(sys.argv[1])
df = pd.DataFrame(data)

# UPSERT sur (po_number, code_article) — colonnes réelles du DDL achat.commande
with engine.begin() as conn:
    for _, row in df.iterrows():
        conn.execute(text("""
            INSERT INTO achat.commande
                (po_number, code_article, fournisseur, prix_unitaire, quantite,
                 etd_confirme, etd_reel, eta, source, updated_at)
            VALUES
                (:po_number, :code_article, :fournisseur, :prix_unitaire, :quantite,
                 :etd_confirme, :etd_reel, :eta, 'gmail', NOW())
            ON CONFLICT (po_number, code_article) DO UPDATE SET
                prix_unitaire = EXCLUDED.prix_unitaire,
                etd_confirme  = COALESCE(EXCLUDED.etd_confirme, achat.commande.etd_confirme),
                etd_reel      = COALESCE(EXCLUDED.etd_reel,      achat.commande.etd_reel),
                eta           = COALESCE(EXCLUDED.eta,           achat.commande.eta),
                source        = 'gmail',
                updated_at    = NOW()
        """), row.to_dict())

logger.info("[SUCCES] %d lignes upsert dans achat.commande", len(df))
```

Appel PowerShell :
```powershell
python C:\Users\<marlene>\dev\Data-Achat\achat_gmail_load.py '<json_data>'
```

> Annotations métier (raisons de retard, notes) → table `achat.commande_annotation`
> (déjà ouverte à platform_team), pas dans `achat.commande`.

## Étape 4 — Tâche planifiée

Via le skill `schedule` : `0 8-18/2 * * 1-5` (toutes les 2h, heures ouvrées).
Prérequis : VPN actif + Cowork ouvert sur le poste de Marlène.

## Prérequis installation

1. Connecteur **Gmail** connecté dans Cowork (compte Marlène).
2. **VPN Stormshield** actif.
3. **Python 3.11** + packages : `sqlalchemy psycopg2-binary pandas` (Key Vault inutile ici).
4. `config/.env` renseigné (`platform_team`, `KEY_VAULT_NAME` vide).
5. GRANT `platform_team` sur `achat.commande` appliqué (sql/20260629_grant_platform_team_commande.sql).
