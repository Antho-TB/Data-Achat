# FUSEAU -- Secours demo locale (DWH Azure injoignable)
_2026-06-23 -- a utiliser si le DWH n'est pas accessible a 14h_

> Principe : l'ETL charge depuis les Excel (Service_Achat), PAS depuis Azure.
> On fait donc tourner FUSEAU sur un PostgreSQL LOCAL, 100% hors-ligne.
> Tous les onglets fonctionnent (dashboard, commandes, fournisseurs, artwork,
> qualite, previsionnel). Seul enrich_from_sylob (hors pipeline) a besoin du DWH.

## Option A -- Docker (le plus rapide, ~10 min)

```powershell
# 1. Postgres local jetable
docker run -d --name fuseau-demo -e POSTGRES_PASSWORD=demo -e POSTGRES_DB=achat_demo -p 5432:5432 postgres:16

# 2. Creer le schema achat (le pipeline ne cree pas le schema lui-meme)
docker exec fuseau-demo psql -U postgres -d achat_demo -c "CREATE SCHEMA IF NOT EXISTS achat;"
```

## Option B -- PostgreSQL deja installe localement
Cree juste la base + le schema avec ton outil habituel (pgAdmin/psql) :
```sql
CREATE DATABASE achat_demo;
\c achat_demo
CREATE SCHEMA IF NOT EXISTS achat;
```

## config/.env de secours (sauvegarde l'actuel avant !)

```
KEY_VAULT_NAME=
PG_HOST=localhost
PG_PORT=5432
PG_DB=achat_demo
PG_USER=postgres
PG_PASSWORD=demo
PG_SSLMODE=disable
DATA_DIR=Service_Achat
API_KEY=demo-key
API_HOST=127.0.0.1
API_PORT=5050
```
> `KEY_VAULT_NAME` VIDE = pas d'appel Azure. `PG_SSLMODE=disable` = pas de SSL (Postgres local).

## Charger + lancer

```powershell
python -m src.scripts.etl.pipeline      # cree les tables/vues + charge depuis les Excel
python run_api.py                        # http://127.0.0.1:5050
```
Verifier `http://127.0.0.1:5050/api/health` -> `db: connected`.

## Notes
- Les GRANTS vers `platform_team` echouent (role absent en local) : c'est attendu,
  le pipeline logue un warning et continue (non bloquant).
- Volumes attendus apres chargement : produit ~1198, commande ~636, artwork ~633,
  qualite ~633, ot_transport ~57.
- Apres la demo, revenir au `.env` Azure (restaurer la sauvegarde) ; `docker rm -f fuseau-demo` pour nettoyer.
```
