# Cartographie des sources de données — Service Achats TB Groupe

> Statut : POC — 2026-06-01  
> Contact métier : Andréa (Achats) · e.georgeon@tb-groupe.fr (Supply Chain)

---

## 1. Sources identifiées

| # | Source | Type | Localisation | Accès | Statut |
|---|--------|------|-------------|-------|--------|
| S1 | **Excel Achats (Andréa)** | Fichier .xlsx | `Z:\Achats\` (réseau local) | NTFS restreint — Achats + Antho | ⚠️ Shadow IT principal |
| S2 | **Sylob ERP** | Base de données ERP | Instance Sylob TB Groupe | API / export à définir | 🔴 Non exploré |
| S3 | **DWH Azure PostgreSQL** | Entrepôt de données | Azure (MyReport) | Compte de service MyReport | 🟡 Pipeline ETL en place (partiel) |
| S4 | **MyReport ETL** | Pipeline Python | `MyReport/src/etl/` | Accès dev | 🟡 Pipeline Achats existant |

---

## 2. Description détaillée

### S1 — Excel Achats (fichier Andréa)

**Rôle** : Référentiel Achats opérationnel, tenu manuellement par Andréa.  
**Valeur** : Mine d'or — contient vraisemblablement : fournisseurs, références articles, prix, délais, conditions, évaluations qualité.  
**Contrainte critique** : Droits NTFS stricts. Toute application terrain (scanner magasinier) qui lirait directement ce fichier crasherait avec `Permission Denied`.  
**Architecture imposée** : Découplage obligatoire extraction ↔ consommation.

**À investiguer** :
- [ ] Nombre d'onglets et leurs noms
- [ ] Colonnes clés par onglet (types, formats)
- [ ] Volume de lignes (ordre de grandeur)
- [ ] Fréquence de mise à jour (quotidienne ? hebdo ?)
- [ ] Présence de formules Excel (calculs embarqués)
- [ ] Données confidentielles à masquer avant exposition

---

### S2 — Sylob ERP

**Rôle** : Système transactionnel — commandes, réceptions, fournisseurs, articles.  
**Valeur** : Source de vérité pour les flux Achats transactionnels (PO, réceptions, factures).

**À investiguer** :
- [ ] Mode d'accès disponible (API REST / ODBC / export planifié)
- [ ] Tables ou exports pertinents pour les Achats
- [ ] Périmètre des données vs Excel d'Andréa (complémentarité ou redondance ?)

---

### S3 — DWH Azure PostgreSQL

**Rôle** : Entrepôt centralisé, cible naturelle pour la donnée Achats structurée.  
**Stack** : PostgreSQL Azure, alimenté par MyReport ETL.

**À investiguer** :
- [ ] Tables Achats déjà présentes (schéma, colonnes)
- [ ] Couverture temporelle (historique disponible)
- [ ] Qualité des données existantes (nulls, doublons)
- [ ] Schéma cible pour accueillir les données Excel

---

### S4 — MyReport ETL

**Rôle** : Pipeline Python existant — aspire les données et les pousse dans le DWH.  
**Localisation** : `MyReport/src/etl/` (non monté dans cette session).

**À investiguer** :
- [ ] Y a-t-il déjà un connecteur Achats/Excel dans ce pipeline ?
- [ ] Identifiants de connexion DWH disponibles (Key Vault ?)

---

## 3. Flux de données actuels (connu)

```
Z:\Achats\[fichier Andréa]  ──┐
                               ├──▶  [GAP] ──▶  DWH PostgreSQL Azure
Sylob ERP ─────────────────────┘
                                         ▲
                               MyReport ETL (partiel)
```

**Gap principal** : L'Excel d'Andréa n'est pas encore intégré dans le DWH de façon fiable et automatisée.

---

## 4. Options d'intégration (rappel Note de Synthèse)

| Option | Mécanisme | Délai mise en œuvre | Complexité | Recommandation |
|--------|-----------|---------------------|------------|----------------|
| **A — ETL MyReport** | Compte de service aspire l'Excel la nuit → DWH | ~1 semaine | Faible | ✅ Court terme |
| **B — Script Python** | Tâche planifiée sur session autorisée → fichier plat / DB locale | ~2 jours | Très faible | ✅ POC immédiat |
| **C — SharePoint + n8n** | Migration fichier → SharePoint, webhook n8n → DWH temps réel | ~2-3 semaines | Moyenne | 🎯 Cible long terme |

**Recommandation POC** : Option B pour valider la structure des données rapidement, puis Option A ou C en production selon la décision avec Andréa.

---

## 5. Prochaines actions pour débloquer l'exploration

| Priorité | Action | Qui | Bloquant pour |
|----------|--------|-----|---------------|
| 🔴 P1 | Partager l'Excel Achats (ou un extrait anonymisé) | Andréa / Antho | Profiling S1, schéma cible |
| 🔴 P1 | Accès en lecture DWH PostgreSQL (credentials ou Key Vault) | Antho | Profiling S3 |
| 🟡 P2 | Monter le dossier `MyReport/` dans cette session | Antho | Audit pipeline S4 |
| 🟡 P2 | Clarifier mode d'accès Sylob (API / export) | Andréa / DSI | Profiling S2 |
