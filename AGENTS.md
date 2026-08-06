# Data-Achat / FUSEAU — Contexte Codex

## Rôle
Dashboard Achats TB Groupe (nom de code **FUSEAU**) — reporting, KPIs achats, détection anomalies. Onglets Article (historique prix), Promo/Opé, Qualité, suivi conteneurs/maritime.

## Statut
**En production** sur le poste de Marlène depuis le 23/07/2026 (mise à jour 28/07/2026).
Démarré comme POC le 28/04, l'app a évolué en backend/frontend déployé sur le poste métier. Ne plus la considérer comme un POC exploratoire ; l'ancien statut "Streamlit/notebook" est obsolète.

**Pilotage : `docs/plan_action.md` est la source de vérité unique.** Il remplace depuis le 28/07 les anciens `TASKS.md` et `TASKS_POSTE_MARLENE.md`, archivés. Ne pas recréer de traceur parallèle.

## Stack réelle
- Backend : FastAPI (`app/main.py`, `run_api.py`, lancé via `uvicorn`)
- Frontend : HTML/JS vanilla (`frontend/index.html`), tables avec tri DOM, pas de framework JS lourd
- DB : PostgreSQL Azure (schéma `achat.*`), migrations SQL versionnées dans `sql/`
- Sources : DWH Azure PostgreSQL (via MyReport ETL) · Sylob ERP · pipeline Gmail (voir skill `achat-gmail-dwh`)
- Déploiement : poste Marlène (voir `deploy/`, `docs/20260629_FUSEAU_DeploiementPosteMarlene_Cowork_v1.md`)

## Contexte
Projet data analytique en amont du DWH MyReport.
Les données brutes viennent de `MyReport/src/etl/` (pipeline Achats déjà en place).

## Coordination métier
Andréa (Assistante Achats, quitte le 31/07/2026), Marlène (Responsable Achats), e.georgeon@tb-groupe.fr (Supply Chain).
Toute nouvelle fonctionnalité prod doit rester validée avec le métier avant généralisation — mais le projet n'est plus en phase d'exploration.

## Standards TB Groupe (obligatoires sur tout fichier prod)
- Python 3.11, type hints partout
- Config centralisée via classe `Config`
- `logger = logging.getLogger(__name__)` via `src.utils.logging_setup.setup_logging()` — jamais `print()`, sauf sortie de données d'un CLI pipeable
- Connexion DB via Key Vault (réutiliser le pattern MyReport)

## Règle d'écriture et de suppression en base (Stricte & Permanente - Toutes sessions)
1. **INTERDICTION ABSOLUE ET STRICTE DE DESTRUCTIFS AUTOMATIQUES :**
   Il est STRICTEMENT INTERDIT d'exécuter toute commande SQL destructive (`DROP TABLE`, `DROP VIEW`, `DROP SCHEMA`, `DROP DATABASE`, `TRUNCATE`, ou `DELETE`) de manière automatique ou scriptée.
   Chaque opération de suppression ou nettoyage de structure/données doit OBLIGATOIREMENT faire l'objet d'une confirmation explicite, écrite et préalable d'Anthony Bezille pour chaque table concernée, sans AUCUNE exception.

2. **Écritures applicatives FUSEAU :**
   `achat.commande` et `achat.qualite` sont rechargées en **full-refresh** (TRUNCATE + INSERT) par l'ETL. Aucun module applicatif ne doit y écrire directement : ce serait effacé au prochain run nocturne.
   - Saisies utilisateur → `achat.commande_annotation`
   - Enrichissements automatiques (réception Sylob, NCR mail) → `achat.commande_enrichissement`
   - Reprojection par `src/scripts/etl/apply_enrichissement.py`, étape ENRICH en fin de `pipeline.py`

## Imported Claude Cowork project instructions

Investiguer tous les workflow du service Achat et structurer la donnée

