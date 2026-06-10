# Plan d'action — ERP Achat TB Groupe
**Date :** 2026-06-09 | **Statut :** POC en cours · pipeline Gmail validé (19 lignes)
**Scope :** Gmail Marlène uniquement pour l'instant · Andréa à connecter en phase 2

---

## Statut opérationnel

| Composant | Statut |
|-----------|--------|
| Pipeline Gmail → `achat.commande` | ✅ Validé (19 lignes, données SOFSI / DEKRA / ONE SWAN / POLYFLAME / DHL) |
| Backend FastAPI (`app/main.py`) | ✅ Codé — à lancer |
| Frontend HTML 5 onglets (`frontend/index.html`) | ✅ Codé — à lancer |
| Contrainte UNIQUE `(po_number, code_article)` | ❌ Manquante — **bloquant upsert** |
| Table `achat.artwork` | ❌ Non créée |
| Table `achat.historique_prix` | ❌ Non créée |
| Serveur de fichiers → DWH | ❌ Pas encore ingéré |

---

## ⚠️ Correction critique

> **Les retards sont sur les ARTICLES, pas les PO**
> Calcul de retard agrégé **par `code_article`**, pas par commande.
> Implémenté dans la vue SQL `achat.v_retard_article` (P3).

---

## Priorités consolidées (ordre d'exécution)

### 🔴 P1 — Contrainte UNIQUE + nettoyage doublons
**Effort :** 1h | **Impact :** déblocage upsert pipeline · **Bloquant pour tout le reste**

```sql
-- 1. Identifier les doublons
SELECT po_number, code_article, COUNT(*) FROM achat.commande
GROUP BY po_number, code_article HAVING COUNT(*) > 1;

-- 2. Supprimer les doublons (garder le plus récent)
DELETE FROM achat.commande a
USING achat.commande b
WHERE a.ctid < b.ctid
  AND a.po_number = b.po_number
  AND a.code_article = b.code_article;

-- 3. Créer la contrainte
ALTER TABLE achat.commande
ADD CONSTRAINT uq_commande_po_article UNIQUE (po_number, code_article);

-- 4. Ajouter colonnes manquantes si nécessaire
ALTER TABLE achat.commande ADD COLUMN IF NOT EXISTS statut_retard VARCHAR(30);
ALTER TABLE achat.commande ADD COLUMN IF NOT EXISTS commentaire TEXT;
```
Scripts dans `00_PILOTAGE/` : `inspect_schema.py`, `add_constraint.py`

---

### 🔴 P2 — Ingérer Matrice TB Import + IMPORT 2026
**Effort :** 2h | **Impact :** onglets Prévisionnel, Commandes, Fournisseurs

| Fichier source | Table cible |
|---------------|-------------|
| `LIS-ACH-53-0-Matrice TB Import.xlsx` | `achat.import_matrice` |
| `IMPORT 2026.xlsx` | `achat.import_2026` |
| `Base article dimensions volume.xlsx` | `achat.article_ref` |

Source de vérité : `\\Srv-files-pom\partage\ADA\METIER\SUIVI CDES IMPORT\PRODUITS\` (poste Marlène, droits AD requis)
Réplica figé 18/03/2026 : `\\Srv-files-pom\partage\DATA\METIER\Achat` (poste Antho)

---

### 🔴 P3 — Calcul retard par article (pas par PO)
**Effort :** 2h | **Impact :** onglet "Suivi commandes" correct

```sql
CREATE OR REPLACE VIEW achat.v_retard_article AS
SELECT
    code_article,
    fournisseur,
    MAX(date_etd)                        AS etd_confirme,
    CURRENT_DATE - MAX(date_etd)         AS jours_retard,
    CASE WHEN MAX(date_etd) < CURRENT_DATE THEN 'EN RETARD'
         ELSE 'DANS LES DELAIS' END      AS statut_retard
FROM achat.commande
WHERE date_etd IS NOT NULL
GROUP BY code_article, fournisseur;
```

---

### 🔴 P4 — Table `achat.historique_prix` + alimentation Gmail
**Effort :** 3h | **Impact :** onglet "Fournisseurs" — besoin n°1 Andréa (historique pas accessible aujourd'hui)

```sql
CREATE TABLE IF NOT EXISTS achat.historique_prix (
    id            SERIAL PRIMARY KEY,
    po_number     VARCHAR(50),
    code_article  VARCHAR(50),
    fournisseur   VARCHAR(100),
    prix          NUMERIC(12,4),
    devise        VARCHAR(10) DEFAULT 'EUR',
    date_mail     DATE,
    source        VARCHAR(20) DEFAULT 'gmail',
    thread_id     VARCHAR(100),
    created_at    TIMESTAMP DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_hp_article      ON achat.historique_prix(code_article);
CREATE INDEX IF NOT EXISTS idx_hp_fournisseur  ON achat.historique_prix(fournisseur);
```

Enrichir le skill `achatanalyser-mail` pour extraire les prix dans un objet séparé → écrire dans `achat.historique_prix` en parallèle de `achat.commande`.
Bootstrap historique : envisager extraction Gmail 12 mois (une seule fois) pour rétropublier.

---

### 🔴 P5 — Ingérer `Demande d'artworks - Clarisse.xlsx` → `achat.artwork`
**Effort :** 1h | **Impact :** onglet "Artwork" — Design / Clarisse

```sql
CREATE TABLE IF NOT EXISTS achat.artwork (
    id              SERIAL PRIMARY KEY,
    code_article    VARCHAR(50),
    designation     VARCHAR(200),
    statut_artwork  VARCHAR(30) DEFAULT 'Aucun',  -- Aucun / Demandé / En cours / Validé / Archivé
    responsable     VARCHAR(100),
    commentaire     TEXT,
    date_demande    DATE,
    updated_at      TIMESTAMP DEFAULT NOW()
);
```

Action immédiate : ouvrir `Demande d'artworks - Clarisse.xlsx` pour mapper les colonnes disponibles.
Le frontend supporte déjà le inline edit → PUT `/api/artwork/{id}`.

---

### 🟡 P6 — Localiser "Suivi des analyses" (Andréa) → `achat.suivi_analyses`
**Effort :** ? | **Impact :** futur onglet "Qualité" | **Bloquant :** chemin fichier inconnu

```sql
CREATE TABLE IF NOT EXISTS achat.suivi_analyses (
    id              SERIAL PRIMARY KEY,
    code_article    VARCHAR(50),
    fournisseur     VARCHAR(100),
    type_analyse    VARCHAR(100),
    statut          VARCHAR(50),
    date_demande    DATE,
    date_resultat   DATE,
    resultat        VARCHAR(50),  -- Conforme / Non-conforme / En attente
    commentaire     TEXT,
    updated_at      TIMESTAMP DEFAULT NOW()
);
```

---

### 🟡 P7 — Vues SQL agrégées par onglet
**Effort :** 4h | **Impact :** tous onglets · performance requêtes

| Vue | Onglet | Dépend de |
|-----|--------|-----------|
| `achat.v_previsionnel` | Prévisionnel | P1, P2 |
| `achat.v_retard_article` | Suivi commandes | P1, P3 |
| `achat.v_stats_fournisseur` | Fournisseurs | P1, P4 |
| `achat.v_artwork_status` | Artwork | P5 |

---

### 🟡 P8 — Lancer ERP local + valider avec le service Achats
**Effort :** 30 min | **Impact :** démo + validation métier

```bash
# Installation dépendances (une seule fois)
pip install -r requirements_api.txt

# Lancement (VPN Stormshield doit être actif)
python run_api.py

# Ouvrir dans le navigateur
http://127.0.0.1:8000
```

---

### 🟢 P9 — Connecter Gmail d'Andréa
**Effort :** 1h setup | **Impact :** onglet Qualité + analyses fournisseurs
- Même démarche que Marlène : Cowork sur son poste + plugin `achat-gmail-pipeline`
- Scope : mails de demande d'analyse + retours laboratoire

---

### 🟢 P10 — Auth + déploiement Azure App Service (prod)
**Effort :** 4h | **Phase :** après validation POC
- Azure AD OAuth2 / MSAL — droits par service (Achats lecture/écriture, Design lecture artwork)
- `az webapp up` ou GitHub Actions → App Service (~20€/mois B1)
- Key Vault `kv-dtpf-prod` à provisionner : alexandre.seccaud@nubo.fr
- Marlène RBAC Key Vault : Object ID `beca8de6-a648-45b1-914c-8c9c31740c14`

---

## Questions ouvertes

| # | Question | Qui | Urgence |
|---|----------|-----|---------|
| Q1 | Chemin exact "Suivi des analyses" sur le serveur | Andréa | 🔴 |
| Q2 | Colonnes disponibles dans `Demande d'artworks - Clarisse.xlsx` | Clarisse / Marlène | 🔴 |
| Q3 | Bootstrap historique Gmail 12 mois pour les prix ? | Antho | 🟡 |
| Q4 | Windows Server interne disponible pour héberger l'ERP avant App Service ? | DSI / Stéphane | 🟡 |

---

## Architecture cible (prod)

```
Gmail Marlène ─────┐
Gmail Andréa  ─────┤ Cowork (MCP Gmail)
Fichier serveur ───┘
        │
        ▼
  Python ETL local Windows (VPN actif)
        │
        ▼
  PostgreSQL Azure — dtpf_sylob_prod · schema achat
  ┌────────────────┬──────────────────┬────────────────────┐
  │ achat.commande │ achat.hist_prix  │ achat.artwork      │
  │ achat.import_* │ achat.article_ref│ achat.suivi_anal.  │
  └────────────────┴──────────────────┴────────────────────┘
        │
        ▼
  FastAPI app/main.py
        │
        ▼
  frontend/index.html
  ┌──────────┬─────────────┬──────────────┬─────────┬──────────────┐
  │ Dashboard│ Commandes   │ Fournisseurs │ Artwork │ Prévisionnel │
  └──────────┴─────────────┴──────────────┴─────────┴──────────────┘
  Lecture + écriture inline → PUT /api/* → PostgreSQL Azure
```
