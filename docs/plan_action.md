# Plan d'action — Système Data-Achat TB Groupe

> Issu de la réunion de cadrage · 2026-06-01  
> Mis à jour : **2026-06-08** (session debug dashboard + push GitHub)  
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
| Clé primaire produit | Code article Sylob (créé par Emmanuelle) → EAN13 dans Sylob (clé de jointure vers `dtpf_sylob_prod` en prod) |
| Avant code article | Code provisoire `JJMMAAHHMM` |
| Interface | HTML statique → Streamlit si besoin d'écriture |
| Email | Gmail MCP — email-first |
| Plugin | Cowork `.plugin` — installable postes Andréa + Marlène |
| Secrets | Azure Key Vault via `DefaultAzureCredential` |
| Connection URL | `sqlalchemy.engine.URL.create()` — gère les caractères spéciaux dans le mot de passe |

---

## Contraintes calendrier (Antho)

| Période | Type | Semaine | Impact projet |
|---------|------|---------|--------------|
| 01/07/2026 (1j) | HSNPM | S27 | Négligeable |
| 13-17/07/2026 | Formation DataScientest | S29 | ⚠️ Semaine bloquée — tampon avant deadline 31/07 |
| **31/07/2026** | **Départ Andréa** | **S31** | **🔴 DEADLINE DURE — validation POC avant cette date** |
| 07/08 + 10-14/08 | Formation DataScientest | S32-S33 | Post-POC |
| 17-31/08/2026 | CP | S34-S35 | Post-POC |
| 01/09/2026 (1j) | HSNPM | S36 | Post-POC |
| 28/09-02/10/2026 | CP | S40 | Post-POC |
| 24-31/12/2026 | CP | S52-S53 | Post-POC |
| Sept → Nov 2026 | Formation DataScientest (récurrent) | S37+ | Phases 3-4 à cadence réduite |

> Formation DataScientest = programme long (jusqu'en 2027). Prévoir ~1-2 jours/semaine bloqués post-POC.

---

## État d'avancement — 2026-06-08

### ✅ Accompli (sessions 2026-06-03 → 2026-06-08)

| Livrable | Statut | Détail |
|---------|--------|--------|
| Cartographie des 4 sources de données | ✅ | `docs/cartographie_sources.md` |
| Profil complet des fichiers Excel Andréa | ✅ | `docs/profil_donnees.md` |
| ETL Python complet (extract + transform + load) | ✅ | `src/scripts/etl/` — pipeline en prod |
| Structure projet aux standards TB Groupe | ✅ | `src/utils/`, `src/scripts/`, `config/` |
| Credentials Key Vault opérationnels | ✅ | `DefaultAzureCredential` → Key Vault → PostgreSQL |
| Connexion TCP PostgreSQL résolue | ✅ | `URL.create()` — problème `@` dans le mot de passe |
| Cartographie DWH Sylob complète | ✅ | 3 sociétés, 16 modules, tables Achat/Article documentées |
| CREATE SCHEMA achat + chargement en prod | ✅ | 720 lignes commande, 1 198 produits |
| Enrichissement Sylob multi-schéma | ✅ | `enrich_from_sylob.py` — cascade GDD → SE → CIE — **99,7% couverture** (884/888 articles SE retrouvés) |
| Dashboard HTML Circuit B | ✅ | `dashboard_achats.html` — KPIs, Chart.js, table filtrée, en cours, historique prix |
| Fix SyntaxError template dashboard | ✅ | `showTab` : adjacent string literals → `getAttribute` loop |
| Push GitHub | ✅ | `Antho-TB/Data-Achat` — commit `60cbb51` |

### 🔴 Bloqué — action requise

| Blocage | Impact | Action |
|---------|--------|--------|
| Accès Gmail Andréa + Marlène | Phase 3 bloquée | Autorisation + MCP Gmail |

### 🟡 Non démarré

| Tâche | Phase | Priorité |
|-------|-------|---------|
| Présentation dashboard à Andréa + Marlène | Phase 1 | 🔥 Mardi 09/06 |
| Validation schéma BDD avec Andréa + e.georgeon | Phase 1 | Haute |
| Analyse 2 fils Gmail Circuit B bout en bout | Phase 1 | Haute |
| Exploration `public` schema dtpf_sylob_prod (54 tables MyReport) | Prérequis prod | Moyenne |
| Streamlit si besoin d'écriture (signalement retard, notes) | Phase 2 | Basse |

---

## Phases

### Phase 0 — Initialisation ✅ (S23, 2026-06-08)

- [x] **Débloquer CREATE SCHEMA** — résolu
- [x] ETL pipeline en prod — 720 commandes, 1 198 produits chargés
- [x] Enrichissement Sylob 3 schémas — 99,7% couverture
- [ ] Analyser 2 fils Gmail Circuit B bout en bout → `process_map_reappro.md`
- [ ] Valider schéma BDD avec Andréa + e.georgeon

### Phase 1 — Circuit B opérationnel ✅ (livré S23, 2 sem. d'avance)

- [x] Lancer `python -m src.scripts.etl.pipeline` en prod
- [x] Explorer `tarrerias_production_dwh` — 3 schémas Article, jointure Sylob
- [x] Croiser données Excel Andréa ↔ données Sylob
- [x] Dashboard HTML v1 : KPIs + Chart.js + table filtrée + en cours + historique prix

**Livrable** : `dashboard_achats.html` — standalone, utilisable sans installation  
**Prochaine étape** : présentation à Andréa + Marlène le 09/06 → itérations sur retours

### Phase 2 — Circuit A + Plugin Cowork (S26-S27, avant 01/07)

> ⚠️ S29 (13-17/07) = formation DataScientest — terminer la phase 2 avant.

- [ ] Analyser 2 fils Gmail Circuit A → `process_map_nouveau_produit.md`
- [ ] Fiche produit collaborative (5 blocs, code provisoire JJMMAAHHMM, photos)
- [ ] Plugin Cowork v0 (skills : nouveau-produit, remplir-bloc, analyser-mail, suivi-commande, historique-prix, verif-doc)

### Phase 3 — Intégration Gmail & cohérence (S30, avant 31/07)

> S29 (13-17/07) = formation DataScientest (semaine bloquée).  
> **Andréa absente à partir du 31/07 -- deadline dure pour la validation.**  
> Phase 3 doit être livrée S30 (20-26/07) pour laisser S31 à la validation.

- [ ] Connecter MCP Gmail (Andréa + Marlène)
- [ ] Parser fils de discussion → enrichir BDD produit
- [ ] Rapport cohérence mail ↔ BDD (incohérences prix, quantités)

### Phase 4 — Vérification documentaire & Paiement (S37+, après 01/09)

- [ ] Comparaison facture fournisseur vs commande Sylob
- [ ] Checklist réglementaire (affichage France/EU, douanes, conteneurs)
- [ ] Interface Compta : BL + packing list + bon réception → validation paiement

---

## Jalons

| Jalon | Semaine | Livrable | Statut |
|-------|---------|---------|--------|
| J0 — Schema `achat` créé + ETL en prod | S23 (08/06) | Premier chargement réel DB | ✅ |
| J1 — Dashboard HTML + données Sylob croisées | S23 (08/06) | `dashboard_achats.html` v1 | ✅ **2 sem. d'avance** |
| J2 — Validation métier + process map Circuit B | S24 (15/06) | Retours Andréa/Marlène + `process_map_reappro.md` | 🔜 Mardi 09/06 |
| J3 — Process map Circuit A validé | S26 (26/06) | `process_map_nouveau_produit.md` | ⏳ |
| J4 — Plugin Cowork v0 | S28 (10/07) | 3 skills opérationnels | ⏳ — doit être fini avant S29 FORM |
| J5 — Intégration Gmail | S30 (24/07) | Cohérence mail ↔ BDD | ⏳ — après S29 FORM |
| **Deadline POC — Andréa part le 31/07** | **31/07/2026 (S31)** | **Validation métier** | ⏳ -- deadline dure, Andréa absente après |
