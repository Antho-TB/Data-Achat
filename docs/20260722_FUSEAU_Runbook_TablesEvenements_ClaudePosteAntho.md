# Runbook — Créer les tables d'événements métier (à exécuter par Claude sur le poste Antho)

> **Pour qui** : Claude sur le poste d'Anthony (`C:\Users\abezille\dev\Data-Achat`), avec l'identité
> **owner/admin** (login perso `dtpf_sylob_anthony_bezille_prod` via `config/.env`).
> **Pourquoi ici** : la création de tables (DDL) doit passer par ton identité contrôlée, pas par
> `platform_team` depuis le poste de Marlène.
> **À exécuter à la lettre, dans l'ordre.** Ne rien improviser sur l'arborescence : elle est figée
> dans le fichier SQL canonique `sql/20260722_tables_evenements_metier.sql`.

## Contexte (1 phrase)
On crée 4 tables `achat.*` pour structurer l'info métier du flux Gmail (non-Sylob), en remplacement
du fourre-tout `achat.commande_annotation` : `qualite_decision`, `transport_evenement`,
`commerce_decision`, `design_evenement`. Détail : `docs/20260722_FUSEAU_Cartographie_FluxGmail_v1.md`.

## Prérequis
1. **VPN Stormshield actif** (DWH Azure injoignable sinon).
2. Repo à jour : `cd C:\Users\abezille\dev\Data-Achat ; git pull`.
3. Venv projet actif (`.venv311`) et `config/.env` = identité owner (login perso Antho).

## Étape 1 — Appliquer la migration DDL
Le fichier `sql/20260722_tables_evenements_metier.sql` contient les 4 `CREATE TABLE IF NOT EXISTS`
(+ index + GRANT vers `platform_team`). Applique-le tel quel, sans le modifier :

```powershell
cd C:\Users\abezille\dev\Data-Achat
.venv311\Scripts\python.exe -c "from app.database import get_engine; from pathlib import Path; r=get_engine().raw_connection(); c=r.cursor(); c.execute(Path('sql/20260722_tables_evenements_metier.sql').read_text(encoding='utf-8')); r.commit(); r.close(); print('OK migration appliquee')"
```

*(Alternative psql, si tu préfères — renseigne les valeurs depuis `config/.env`) :*
```powershell
$env:PGPASSWORD = "<PG_PASSWORD depuis .env>"
& "C:\Program Files\PostgreSQL\16\bin\psql.exe" -h <PG_HOST> -p <PG_PORT> -U <PG_USER> -d <PG_DB> -f "sql\20260722_tables_evenements_metier.sql"
```

## Étape 2 — Vérifier
```powershell
.venv311\Scripts\python.exe -c "from app.database import get_engine; from sqlalchemy import text; e=get_engine();
import sys
with e.connect() as c:
    for t in ('qualite_decision','transport_evenement','commerce_decision','design_evenement'):
        n=c.execute(text(f'select count(*) from achat.{t}')).scalar()
        print(t,'OK, lignes =',n)"
```
Attendu : les 4 tables existent, 0 ligne. Si une table manque → relire Étape 1.

## Étape 3 — Committer (depuis ton poste, jamais le sandbox)
La migration `.sql` est déjà versionnée. Rien à committer pour le DDL lui-même s'il est déjà sur `main`.
Vérifie juste : `git log --oneline -3` doit contenir le commit de `sql/20260722_tables_evenements_metier.sql`.

## Étape 4 — Activer la captation structurée (DML — peut aussi se faire depuis le poste de Marlène)
Une fois les tables créées :
1. Le loader routeur existe déjà : `src/scripts/gmail/load_evenements.py` (route chaque enregistrement
   vers la bonne table selon `domaine` ∈ {qualite, transport, commerce, design} ; idempotent via `cle_idempotence`).
   Test à blanc : `.venv311\Scripts\python.exe -m src.scripts.gmail.load_evenements --file data\_evenements.json --dry-run`
2. **Rerouter la tâche planifiée Cowork** `fuseau-gmail-threads-achat` : elle doit produire des
   enregistrements structurés (avec `domaine` + champs par sujet) et appeler `load_evenements.py`
   au lieu de `load_annotations.py`. (Mise à jour du prompt de la tâche à faire côté Cowork — voir
   `TASKS_POSTE_MARLENE.md`.) `commande_annotation` reste pour le divers non classé.

## Résultat attendu
4 tables `achat.*` structurées par sujet, alimentées par le flux Gmail, conformes au principe
« achat.* = uniquement le non-Sylob ». Fin du fourre-tout `commande_annotation` pour ces 4 sujets.
