# Data-Achat / FUSEAU — Contexte Claude

## Rôle
Dashboard Achats TB Groupe (nom de code **FUSEAU**) — reporting, KPIs achats, détection anomalies. Onglets Article (historique prix), Promo/Opé, Qualité, suivi conteneurs/maritime.

## Statut
**Application déployée** (poste Marlène) — dépassé le stade POC (mise à jour 21/07/2026).
Historique : démarré comme POC le 28/04/2026 ; l'app a depuis évolué vers un vrai backend/frontend avec déploiement sur le poste métier. Ne plus considérer ce projet comme un simple POC exploratoire — l'ancien statut "Streamlit/notebook" est obsolète.

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
- `logger = logging.getLogger(__name__)` — jamais `print()`
- Connexion DB via Key Vault (réutiliser le pattern MyReport)
