# Plan d'action — Système Data-Achat TB Groupe

> Issu de la réunion de cadrage · 2026-06-01  
> Mis à jour : 2026-06-03 (post-its équipe Achat intégrés)  
> Périmètre : Achats Import · Utilisateurs finaux : Andréa, Marlène, Olivier, Eric, Charles, David, Jonatan, Julia, Emmanuelle

---

## Acteurs identifiés

| Personne | Service | Rôle dans le process |
|----------|---------|---------------------|
| **Andréa** | Achats | Coordinatrice, passe les commandes dans Sylob |
| **Marlène** | Achats | Collaboratrice Andréa, co-utilisatrice du système |
| **Olivier** | Appro | Réappro des produits existants (suggestion d'appro) |
| **Emmanuelle** | Logistique / Supply Chain | Crée le code article dans Sylob, bloc PCB/SPCB/EAN |
| **Eric** | Commerce | Bloc commercial de la fiche achat (prix, client) |
| **Charles** | Commerce | Commerce — avec Eric et David |
| **David** | Commerce | Commerce — avec Eric et Charles |
| **Jonatan** | Produit | Bloc nom article FR/EN, gamme |
| **Julia** | Sourcing | Bloc infos China (fournisseur, production, conformité) |
| **Design** | Design | Bloc packaging, dimensions, visuels, marquage, artwork, validation boîte |
| **TB China** | Intermédiaire | Relais fournisseurs Chine — reçoit PO signé + PS signé + Artwork |
| **Transitaire** | Logistique externe | Transport / dédouanement — fournit ETD, ETA, alertes retard |
| **DEKRA** | Contrôle qualité | Inspections, rapports de conformité |
| **Labo / Qualité** | Qualité interne | Commandes d'analyse + rapports d'analyses (multiple étapes) |
| **Logistique** | Logistique interne | Reçoit le planning de livraison envoyé par Andréa — anticipe besoins humains, matériels et temps |
| **(Douanes)** | *(via Transitaire)* | *Géré par le transitaire — pas un acteur direct du service Achat* |
| **Samuel** | IT Réseau | VPN Stormshield S2S |
| **Compta** | Finance | Paiement fournisseurs (BL + Facture + Packing list) — Phase 2 |

---

## Les deux circuits distincts

### Circuit B — Réappro (produit existant)
> Quotidien, volume élevé, données déjà disponibles — **PRIORITAIRE**

```
Olivier (suggestion d'appro : besoin X unités de l'article Y)
        │
        ▼
Andréa  →  Commande dans Sylob  ←  email fournisseur (email-first)
        │
        ▼
Suivi import (IMPORT 2026) :
  TB China · Transitaire · DEKRA · N° conteneur · BL · N° facture
        │
        ▼
Livraison  →  Vérification doc (BL / facture / packing list)
        │
        ▼
Compta (BL + packing list + bon réception → paiement)   ← Phase 4
```

### Circuit A1 — Composants GDD (Général de Découpage) — allégé
> Achat de composants pour l'usine GDD (molettes, ressorts, etc.)  
> **PAS de fiche achat** — tout est déjà dans Sylob, référence déjà créée  
> La fiche achat template existe mais n'est jamais utilisée (produits trop différents entre eux) — à traiter ultérieurement

```
GDD (Olivier Bertrand) → Demande d'achat dans Sylob
        │  (référence déjà créée, données déjà dans Sylob)
        ▼
Service Achat = suivi uniquement (pas de création de fiche)
        │
        ▼
Commande fournisseur → Réception composant
```

Deux sous-cas :
- **Nouveau composant GDD** : demande d'achat Sylob → réf déjà créée → suivi Achat
- **Réappro composant GDD** : même circuit, encore plus simple

### Circuit A2 — Nouveau produit Chine (Import)
> Ponctuel, multi-service, processus long — **Phase 2**

Workflow reconstitué depuis le board post-its équipe Achat :

```
SERVICE ACHAT
  Réception besoin nouveau produit → Négocier prix / Demander création référence
        │
        ▼ [CHARLES/ERIC/DAVID — Commerce]    [DESIGN]
  Créer fiche achat ─────────────────── Matière, Dimensions, Marquage, Artwork,
        │                               Matière/Dimensions Fournisseur
        ▼
  Créer la commande frs (Sylob)
        │
        ▼ [COMMERCE : Dossier PO et PS]
  Valider la commande
        │
        ▼
  Envoyer la commande  →  [TB CHINA : PO signé + PS signé + Artwork]
        │                 [DESIGN : Etiquettes, Shipping mark, Artwork, Marquage]
        ▼
  Mettre à jour TB Import
        │
        ▼
  Contrôler proforma et signer      ← document Proforma fournisseur
        │
        ▼
  Valider infos et docs
        │
        ▼ [LABO/QUALITÉ : Commande d'analyse + Rapport]
  Réceptionner MAT/SP (matière / semi-produit)  ← A1 spécifique
        │
        ▼ [LABO : Rapport d'analyses]  [DESIGN : Validation produit/impression/dimensions boîte]
  Envoyer rapport analyses + mise à jour TB Import
        │
        ▼
  Réceptionner échantillon conformité
        │
        ▼ [LABO : Rapport d'analyses]  [DESIGN : Validation de la boîte imprimée]
  Envoyer rapport + mise à jour TB Import
        │
        ▼
  Réceptionner échantillon production + vérifier
        │
        ▼ [DEKRA : Demande inspection + Commande inspection → Rapport inspection]
  Vérifier infos + faire commande inspection
        │
        ▼ [TRANSITAIRE : ETD, ETA, Retard imprévu]  [LOGISTIQUE : Planning livraison 1 sem. avant]
  Vérifier infos + valider + envoi produit
  BL + Facture + Packing list
        │
        ▼
  Vérifier infos + mise à jour TB Import + suivi maritime
  BL + Facture + Packing list
        │
        ▼
  Mettre à jour suivi maritime
        │
        ▼
  Annoncer livraison conteneur   ← [(Douanes via Transitaire)]
        │
        ▼  Andréa envoie planning de livraison → [LOGISTIQUE : anticipe besoins humains/matériels/temps]
  Réceptionner échantillon de réception   ← [LOGISTIQUE]
        │
        ▼
Emmanuelle crée le CODE ARTICLE dans Sylob  →  PK définitive
        │
        ▼
→ Rejoint le Circuit B (réappro)
```

---

## Gaps identifiés — board post-its équipe Achat (2026-06-03)

Éléments absents de notre modèle initial, découverts sur le board :

| Élément | Type | Impact BDD / Système |
|---------|------|----------------------|
| **Charles + David** | Acteurs Commerce (avec Eric) | Mettre à jour les blocs fiche achat |
| **Logistique** — rôle clarifié | Acteur | Reçoit le planning de livraison d'Andréa pour anticiper (humains, matériels, temps) |
| ~~**Douanes**~~ | Supprimé | Géré par le transitaire, pas un acteur Achat direct |
| **Proforma** (contrôler + signer) | Document | Ajouter `doc_proforma` dans `achat.commande` |
| **PS signé** (Purchase Sheet) | Document | Notre fiche achat fournisseur — à tracker |
| **Rapport d'analyses** (multiple étapes) | Étape processus | Table `analyse` distincte (labo qualité) |
| **Commande d'analyse** | Document | Lié à chaque checkpoint qualité |
| **MAT/SP** (Matière/Semi-produit) | Étape Circuit A1 | Spécifique usine GDD — pas China import |
| **Validation boîte imprimée** | Étape Design | Checkpoint packaging |
| **Etiquettes + Shipping marks** | Données produit | Champs manquants dans `achat.produit` |
| **Planning livraison 1 semaine avant** | Alerte | À intégrer comme notification dans le dashboard |
| **ETD/ETA/Retard imprévu** géré par Transitaire | Info source | Transitaire = source de vérité ETD/ETA |

---

## Décisions techniques arrêtées

| Décision | Choix |
|----------|-------|
| BDD cible | `dtpf_sylob_prod` schéma `achat` (Azure PostgreSQL) |
| Source DWH Sylob (POC) | `tarrerias_production_dwh` — données brutes Sylob directes |
| Source DWH Sylob (prod) | `dtpf_sylob_prod` schéma `public` — quand MyReport terminé + validation Emmanuelle |
| Clé primaire produit | Code article Sylob (créé par Emmanuelle) |
| Avant code article | Code provisoire `JJMMAAHHMM` |
| Interface | HTML statique → Streamlit si besoin d'écriture |
| Email | Gmail MCP — email-first |
| Plugin | Cowork `.plugin` — installable postes Andréa + Marlène |
| Secrets | Azure Key Vault via `DefaultAzureCredential` |
| Connection URL | `sqlalchemy.engine.URL.create()` — gère les caractères spéciaux dans le mot de passe |

---

## État d'avancement — 2026-06-03

### ✅ Accompli cette session

| Livrable | Statut |
|---------|--------|
| Cartographie des 4 sources de données | ✅ `docs/cartographie_sources.md` |
| Profil complet des fichiers Excel Andréa | ✅ `docs/profil_donnees.md` |
| Prise de note réunion intégrée | ✅ Architecture multi-blocs, PK code article |
| ETL Python complet (extract + transform + load) | ✅ `src/scripts/etl/` — testé dry-run |
| Structure projet aux standards TB Groupe | ✅ `src/utils/`, `src/scripts/`, `config/`, `data/`, `docs/` |
| Credentials Key Vault opérationnels | ✅ `DefaultAzureCredential` → Key Vault → PostgreSQL |
| Connexion TCP PostgreSQL résolue | ✅ `URL.create()` — problème `@` dans le mot de passe corrigé |
| Cartographie DWH Sylob complète | ✅ 3 sociétés, 16 modules, tables Achat/Article/Fournisseur documentées |

### 🔴 Bloqué — action requise

| Blocage | Impact | Action |
|---------|--------|--------|
| `CREATE SCHEMA achat` — permission denied | ETL ne peut pas écrire en DB | Exécuter en pgAdmin avec credentials platform_team, OU PR Terraform sur repo `DTPF-PostgreSQL` |
| Accès Gmail Andréa + Marlène | Phase 3 bloquée | Autorisation + MCP Gmail |

### 🟡 Non démarré

| Tâche | Phase |
|-------|-------|
| Analyse 2 fils Gmail Circuit B bout en bout | Phase 0 |
| Validation schéma BDD avec Andréa + e.georgeon | Phase 0 |
| Exploration `public` schema dtpf_sylob_prod (54 tables MyReport) | Prerequis Phase prod |
| Exploration tables Achat/Fournisseur/Article sur tarrerias_production_dwh | Phase 1 |

---

## Phases

### Phase 0 — Initialisation (S23, 2026-06-08)

- [ ] **Débloquer CREATE SCHEMA** : pgAdmin platform_team OU PR Terraform `DTPF-PostgreSQL`
- [ ] Analyser 2 fils Gmail Circuit B bout en bout → `process_map_reappro.md`
- [ ] Valider schéma BDD avec Andréa + e.georgeon

### Phase 1 — Circuit B opérationnel (S24-S25, 2026-06-15)

- [ ] Lancer `python -m src.scripts.etl.pipeline` en prod (schéma `achat` créé)
- [ ] Explorer `tarrerias_production_dwh` — requêter `vue_commande_achat`, `af_fournisseur`, `af_article`
- [ ] Croiser données Excel Andréa ↔ données Sylob (fournisseurs, articles)
- [ ] Prototype HTML v0 : suivi commandes + historique prix + recherche dynamique

**Livrable** : `dashboard.html` v0 — utilisable par Andréa et Marlène sans installation

### Phase 2 — Circuit A + Plugin Cowork (S26-S28, 2026-06-29)

- [ ] Analyser 2 fils Gmail Circuit A → `process_map_nouveau_produit.md`
- [ ] Fiche produit collaborative (5 blocs, code provisoire JJMMAAHHMM, photos)
- [ ] Plugin Cowork v0 (skills : nouveau-produit, remplir-bloc, analyser-mail, suivi-commande, historique-prix, verif-doc)

### Phase 3 — Intégration Gmail & cohérence (S29-S30, 2026-07-13)

- [ ] Connecter MCP Gmail (Andréa + Marlène)
- [ ] Parser fils de discussion → enrichir BDD produit
- [ ] Rapport cohérence mail ↔ BDD (incohérences prix, quantités)

### Phase 4 — Vérification documentaire & Paiement (après 31/07/2026)

- [ ] Comparaison facture fournisseur vs commande Sylob
- [ ] Checklist réglementaire (affichage France/EU, douanes, conteneurs)
- [ ] Interface Compta : BL + packing list + bon réception → validation paiement

---

## Jalons

| Jalon | Semaine | Livrable |
|-------|---------|---------|
| J0 — Schema `achat` créé + ETL en prod | S23 (08/06) | Premier chargement réel DB |
| J1 — Process map Circuit B + schéma validé | S23 (08/06) | `process_map_reappro.md` |
| J2 — Dashboard HTML v0 + données Sylob croisées | S25 (22/06) | `dashboard.html` v0 |
| J3 — Process map Circuit A validé | S26 (29/06) | `process_map_nouveau_produit.md` |
| J4 — Plugin Cowork v0 | S28 (13/07) | 3 skills opérationnels |
| J5 — Intégration Gmail | S30 (27/07) | Cohérence mail ↔ BDD |
| **Deadline POC** | **31/07/2026** | **Validation métier** |
