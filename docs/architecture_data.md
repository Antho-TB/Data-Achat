# Architecture Data Globale (TB Groupe)

Le flux de la donnée suit une logique d'hybridation (On-Premise ➡️ Cloud Azure) avec une séparation stricte des responsabilités entre l'ERP, la BI officielle (MyReport), et l'innovation métier (Data-Achat).

```mermaid
graph TD
    subgraph "🏢 Réseau Local (On-Premise)"
        A[ERP Sylob 9] -->|ETL Natif / Interne| B[(DWH Sylob \n On-Premise / Infocentre)]
    end

    subgraph "☁️ Cloud Azure (VNet Privé)"
        B -->|ETL MyReport\nAurélien & Olivier| C[(Azure PostgreSQL Flexible\n dtpf_sylob_prod)]
        
        subgraph "PostgreSQL: Schémas logiques"
            C -.-> D[ssylob9_*\n(DÉPRÉCIÉ - Obsolète)]
            C -.-> E[alz_*\nTables d'entraînement Alizés]
            F[Fichiers Excel Andréa] -->|ETL Python Antho| G[achat.*\nFUSEAU -- applicatif deploye]
            H[n8n + Gmail\nTemps Réel] -.->|Cible Future| G
        end
    end

    subgraph "🔐 Tunnel Réseau"
        VPN[VPN IPSec Stormshield S2S]
    end

    B -.->|Traverse le VPN| C
```

## Explications Techniques

**1. La chaîne de valeur historique (Sylob → MyReport)**
La donnée naît dans l'ERP Sylob. Elle est d'abord extraite vers un DWH Sylob local (On-Premise). L'outil MyReport pompe ce DWH local et pousse la donnée dans le cloud sur Azure PostgreSQL.

**2. Le cloisonnement dans Azure PostgreSQL (`dtpf_sylob_prod`)**
Le DWH Cloud est divisé en 3 schémas étanches :
- `ssylob9_*` : [OBSOLÈTE] Anciennes tables brutes. N'est plus alimenté par les exécutions de l'ETL.
- `alz_*` : [FORMATION] Tables d'entraînement liées au module de formation Alizés de MyReport. Pas de la prod fiable.
- `achat.*` : Le bac à sable sécurisé pour le projet Data-Achat.

**3. La sécurité et le Réseau (IP 172.31.2.5)**
Le DWH Azure vit dans un VNet fermé. L'accès nécessite le VPN IPSec Stormshield. Les Sandbox isolées échoueront à s'y connecter sans proxying par l'hôte Windows.

**4. La vision cible (Event-Driven)**
À terme, n8n écoutera Gmail en temps réel pour parser les documents (ARC, commandes) et viendra enrichir `achat.*` de manière autonome.
