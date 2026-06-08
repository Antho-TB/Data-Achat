# Data-Achat — Contexte Claude

## Rôle
Analyse et pilotage des achats TB Groupe — reporting, KPIs achats, détection anomalies.

## Statut
**POC en cours** (28/04/2026)

## Stack
- Python 3.11 (cible)
- Sources : DWH Azure PostgreSQL (via MyReport ETL) · Sylob ERP
- Streamlit ou notebook (exploration)

## Contexte
Projet data analytique en amont du DWH MyReport.
Les données brutes viennent de `MyReport/src/etl/` (pipeline Achats déjà en place).

## ⚠️ Projet POC
Ne pas industrialiser avant validation métier.
Coordonner avec e.georgeon@tb-groupe.fr (Supply Chain) pour les besoins.

## Standards TB Groupe (à appliquer dès le premier fichier prod)
- Python 3.11, type hints partout
- Config centralisée via classe `Config`
- `logger = logging.getLogger(__name__)` — jamais `print()`
- Connexion DB via Key Vault (réutiliser le pattern MyReport)
