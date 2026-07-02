# Plan d'action -- Système Data-Achat TB Groupe

> Issu de la réunion de cadrage · 2026-06-01  
> Mis à jour : **2026-06-30** (session FUSEAU : contrainte UNIQUE vérifiée prod + fix lignes de frais ; voir État 30/06). Précédent : 23/06 (onglets Qualité + Prévisionnel enrichi).  
> Périmètre : Achats Import · Utilisateurs finaux : Andréa, Marlène, Olivier, Eric, Charles, David, Jonatan, Julia, Emmanuelle

---

## 🔗 Démarrage rapide & liens utiles

**Lancer l'ERP FUSEAU (local) :**
```
cd C:\Users\abezille\dev\Data-Achat
python run_api.py
```
Laisser la fenêtre ouverte (le serveur tourne tant qu'elle l'est).

| Ressource | Lien / commande |
|-----------|-----------------|
| ERP FUSEAU (UI) | http://127.0.0.1:5050 |
| Health check (avant démo) | http://127.0.0.1:5050/api/health → `write_enabled: true` + DWH connecté |
| Workflow n8n PJ Gmail | http://192.168.102.36:5678/workflow/j2HdoDnRAFgG81w2 |
| Repo GitHub | `Antho-TB/Data-Achat` |
| Relancer l'ETL | `python -m src.scripts.etl.pipeline` (`--dry-run` pour tester sans DB) |
| Fetch PJ Gmail (Plan A) | `python -m src.scripts.gmail.fetch_attachments --dry-run` |

**Prérequis :** VPN Stormshield actif (sinon DWH injoignable). Si le port 5050 est occupé par un worker orphelin :
```
Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -match 'run_api|spawn_main' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }
```

---

## ✅ Tâches Antho -- demain 23/06 (à cocher)

> Préparées en session : code Plan A/B livré et testé, runbook OAuth prêt.

**Avant la démo équipe métier**
- [ ] VPN Stormshield actif + relancer l'API proprement (purger les workers uvicorn orphelins : `Get-CimInstance ... -match 'run_api|spawn_main'`).
- [ ] `GET /api/health` → vérifier `write_enabled: true` + DWH connecté.
- [ ] Contrôler le KPI `valeur_totale` (outlier 65,6 M€ identifié à l'ADR -- vérifier avec le métier avant de l'afficher).
- [ ] Démo Circuit B : KPIs, commandes/filtres, prévisionnel retards, historique prix, artwork.

**Branchement poste Marlène + Gmail (Plan A)**
- [ ] Exécuter le runbook OAuth : `docs/20260622_FUSEAU_RunbookOAuthGmail_v1.md` (projet GCP → Gmail API → consent Internal → client desktop → `credentials.json`).
- [ ] Installer **Tesseract OCR** sur le poste (requis pour `load_qualite_analyse_ocr.py` en routine — cf. pilote SPECTRO 02/07, `docs/plan_action.md` item #7).
- [ ] Créer le label Gmail **`Achats/Fournisseurs`** (+ filtre auto sur expéditeurs) -- ou ajuster `GMAIL_LABEL`.
- [ ] `pip install -r requirements-gmail.txt` puis `python -m src.scripts.gmail.fetch_attachments --dry-run` (consentement Marlène).
- [ ] Vérifier le dépôt des PJ, puis run sans `--dry-run`.
- [ ] Mesurer le « quasi » : PO de l'IMPORT sans fil retrouvé chez Marlène.

**Workflow n8n (Plan B)**
- [ ] Dans l'UI n8n (workflow `j2HdoDnRAFgG81w2`) : binder le credential Gmail (Marlène), monter le partage sur `/data/PJ`, activer.

**Suivi maritime (ot_transport)**
- [ ] Obtenir l'accès `\\Srv-files-pom\...\SUIVI CDES IMPORT\2026\TRANSITAIRE\` → renseigner `SUIVI_MARITIME_PATH` → relancer l'ETL (bascule auto du mode dégradé vers le fichier transitaire).

**Communication**
- [ ] Échanger avec Stéphane (s.guillaumont) sur la limite MCP des PJ Gmail (cf. mail préparé).

---

## État FUSEAU au 23/06 (présenté en démo)

> Base peuplée (DWH Azure, schéma achat) : produit 1198, commande 636, artwork 633,
> qualite 633, ot_transport 57, v_previsionnel 636, v_qualite_fournisseur 25.

### ERP multi-onglets -- 6 onglets opérationnels

| # | Onglet | État |
|---|--------|------|
| 1 | Dashboard (KPIs + graphs) | ✅ |
| 2 | Suivi commandes (statut retard par article, filtres, drill-down) | ✅ |
| 3 | Fournisseurs (historique prix par article ou fournisseur) | ✅ |
| 4 | Artwork (statuts design Clarisse) | ✅ |
| 5 | **Qualité** (éval fournisseurs : inspection/NCR/réception + checkpoints MAT/SP/BAT) | ✅ nouveau |
| 6 | **Prévisionnel enrichi** (acheté / à payer / en inspection / parti / en retard / livré + ventilation par fournisseur) | ✅ nouveau |

- ✅ Retards sur ARTICLES, pas PO : vue `v_retard_article`.
- ✅ "En inspection" résolu en joignant `achat.qualite` -- pas d'extension de `achat.commande` nécessaire.
- ✅ Montants : PU x qté (jamais `total_prix`, qui est un SUMIF par PO). Total acheté ~4,0 M€.

### Reste à faire (post-démo)

| Chantier | Détail |
|---|---|
| Bornage de dates (jjmmaa ET anmois) | non implémenté ; le prévisionnel agrège par mois en dur |
| Sous-vue retards par fournisseur dédiée | partiellement couvert par la table fournisseur du prévisionnel |
| Drill-down commande -> produit | handlers présents, valider/compléter le détail retard au clic |
| Qualité -- volet "Suivi des analyses" par mail | la table couvre inspections/NCR ; le flux mail (Andréa -> parties prenantes) reste à câbler |
| Graphs pilotés par le ruban + filtres "ligne 3" | à valider/affiner en visuel |
| Gmail réel (PJ) + n8n | code prêt (Plan A/B), attend OAuth + credential + label |
| Ingestion SUIVI MARITIME (ETD/ETA réels) | attend l'accès dossier transitaire ; `ot_transport` en mode dégradé (cache IMPORT) |
| Archi DNS conditionnel (IP Azure) | différée ; l'IP fixe recassera à la prochaine maintenance Azure |

---

## Lot 3 -- enrichissements Sylob (avancement 25/06)

### Acompte verse -- FAIT (source IMPORT, confirmee metier)
- Table `achat.acompte` creee + `src/scripts/etl/enrich_acompte.py` (lecture Sylob 3 societes,
  jointure `commande_numero_de_la_commande` = `po_number` zero-padde 8, dedoublonnage inter-societes).
- **100 PO apparies** (14 GDD + 86 SE ; 1 collision Cie fusionnee).
- ⚠️ **Au niveau COMMANDE, l'acompte = 0 pour tous nos PO import** (`commande_montant_de_l_acompte`
  non renseigne). Des acomptes existent au niveau **FACTURE** (`vue_facture_achat.facture_montant_de_l_acompte`).
- VERIFIE (25/06) : acompte VIDE pour nos PO aux niveaux commande, facture (via facture_id_commandeachat),
  et avance fournisseur. Seul `frn_pourcentage_d_acompte` est rempli (POLITIQUE %, ex. 30%), pas un montant.
  => Le montant REELLEMENT VERSE n'est pas dans le module Achat Sylob. A localiser cote compta/reglement
  ou Excel Andrea. Option dispo : "acompte ATTENDU" = pct x total_ht (calculable, mais % rempli pour peu de frs).
- RESOLU (25/06) : Marlene saisit les virements (acompte + solde) dans IMPORT 2026 (colonne 'Acompte').
  -> transform_acompte + load_acompte (full-refresh achat.acompte depuis l'Excel ; enrich Sylob abandonne
  pour le montant). 101 PO, 9 avec montant. Expose en colonne "Acompte ($)" dans Suivi commande.
  Compta ne controle qu'au lettrage (fin de process).

### CA fournisseur cumule -- FAIT
- Table `achat.fournisseur_ca` + `src/scripts/etl/enrich_ca.py` (UNION 3 societes, SUM(commande_total_ht)
  sur 3 ans glissants, mapping nom<->frn via le join PO). 24 fournisseurs enrichis.
- Expose dans l'onglet Fournisseurs (colonne "CA 3 ans ($)"). Ex : HONGXING 4,35 M$, SURPASS 1,47 M$.
- ⚠️ Limite : 2 noms Excel partageant 1 meme code Sylob (GUANGWEI / DIAMOND TRACK = frn 00001220)
  recoivent le MEME CA (double-attribution). A arbitrer avec le metier (alias fournisseur ?).

### Historique 3 dernieres commandes par article/fournisseur -- a faire
- Calculable depuis achat.commande (date_commande, prix_unitaire) + extension Sylob si historique > IMPORT 2026.

## Retours démo 2 -- équipe métier (25/06)

Légende : [QW] quick win · [M] touche modèle/intégration · [DEC] décision requise.

### Corrections de justesse (prioritaire)
- [QW] **Retard cumulé** : `CURRENT_DATE - ETD` croît indéfiniment pour les commandes livrées (biais hérité de l'Excel =AUJOURDHUI). FUSEAU doit figer le retard à la livraison (date_livraison - ETD) et exclure les clôturées du "retard moyen fournisseur".
- [DEC] **Montants en USD** : confirmer la devise source (PU import = USD ?) et tout afficher en dollars (montant exact).

### Suivi commande
- [QW] Afficher la **désignation article** (langage métier) ; tri par commande.
- [QW] Différencier **EN RETARD en cours de livraison** vs **EN RETARD pas encore parti** (action possible : appeler TB China).
- [M] Raisons des retards (champ commentaire via `commande_annotation`).
- [chantier] Alertes imprévu majeur (grève, incident) ; notion de **chemin critique** + alerte.
- Statut "réception de commande" = actif tant que le contrôle qualité n'est pas fini (quarantaine pendant inspection).

### Qualité par produit
- [QW] Colonne **N° inspection** (déjà en base : `ref_rapport`).
- [QW] Colonne **N° de commande** (`po_number`, déjà en base).
- [QW] Filtre **BAT** en plus de OK/FAIL.
- [M] Clic sur **FAIL** -> ouvrir le rapport DEKRA dans le Drive (nom du fichier = N° inspection).
- [M] Colonne **décision post-FAIL** (après branchement boîte mail).
- [M] Statut **analyse labo** (taux chrome / dureté) conforme/non conforme -- rapport labo GDD par mail -> Drive, trié par commande, colonne à côté de MAT.

### Prévisionnel / paiement
- [DEC] Règle de **retard de paiement** : à clarifier (payer à l'ETD réel ?).
- [DEC] Montant exact en **USD**.
- [M] Vue **paiement par CONTENEUR** (paiement selon BL ; le paiement déclenche la libération douane). Afficher le(s) BL par conteneur + flag **promo** (urgence).
- [M] Colonne **acompte versé** (source Sylob -- les fournisseurs réclament parfois le total en oubliant l'acompte).

### Fournisseurs
- [M] Bornage temporel + **CA réalisé** avec le fournisseur sur 3 ans (source à définir).
- [QW/M] Historique prix : **3 dernières commandes**, filtre article ET fournisseur.

### Nouveaux onglets
- [chantier] **Article** : suivi achat par article (gère le changement de fournisseur).
- [chantier] **Promo** : opé fidélité, promo, commande initiale nouveau client (ex. COSTCO).

### Process / Gmail
- Marlène est en copie mais **ne reçoit pas tout** ce qu'Andréa reçoit -> pour l'ingestion, cibler la boîte d'Andréa (ou délégation), sinon trous. Confirme la reco précédente.

### Décisions (tranchees 25/06)
1. **Devise** : les montants sont **deja en USD** -> afficher en $ (pas de conversion, juste relabel).
2. **Accès Drive** : liste demandee a Andrea par mail (DEKRA, labo GDD, Suivi artworks, SUIVI MARITIME, Suivi analyses). En attente des liens.
3. **Acompte** : source Sylob = `vue_commande_achat.commande_montant_de_l_acompte` (+ `_devise_societe`, `commande_pourcentage_d_acompte`), present dans les 3 societes :
   `TARRERIAS_GENERALE_DE_DECOUPAGE_Achat` (GDD), `TARRERIAS_SE_TARRERIAS_BONJEAN_Achat` (SE), `TARRERIAS_TARRERIAS_BONJEAN_ET_CIE_Achat` (Cie).
   -> UNION sur les 3 schemas + jointure par n° commande (meme cascade que enrich_from_sylob).
4. **CA fournisseur** : = **achats cumules** par fournisseur/an, UNION des 3 societes Achat (vue_commande_achat), 3 ans glissants.

---

## Acteurs identifiés

| Personne | Service | Rôle dans le process |
|----------|---------|---------------------|
| **Andréa** | Achats | Coordinatrice, passe les commandes dans Sylob |
| **Marlène** | Achats | Collaboratrice Andréa, co-utilisatrice du système |
| **Olivier** | Appro | Réappro des produits existants (suggestion d'appro) |
| **Emmanuelle** | Supply Chain & Data Analyst | Crée le code article dans Sylob (dès la commande frns, prérequis = gamme), bloc PCB/SPCB/EAN |
| **Eric** | Commerce | Bloc commercial de la fiche achat (prix, client) |
| **Charles** | Commerce | Commerce -- avec Eric et David |
| **David** | Commerce | Commerce -- avec Eric et Charles |
| **Jonatan** | Produit | Bloc nom article FR/EN, gamme |
| **Julia** | Sourcing | Bloc infos China (fournisseur, production, conformité) |
| **Design** | Design | Bloc packaging, dimensions, visuels, marquage, artwork, validation boîte |
| **TB China** | Intermédiaire | Relais fournisseurs Chine -- reçoit PO signé + PS signé + Artwork |
| **Transitaire** | Logistique externe | Transport / dédouanement -- fournit ETD, ETA, alertes retard |
| **DEKRA** | Contrôle qualité | Inspections, rapports de conformité |
| **Labo / Qualité** | Qualité interne | Commandes d'analyse + rapports d'analyses (multiple étapes) |
| **Logistique** | Logistique interne | Reçoit le planning de livraison envoyé par Andréa -- anticipe besoins humains, matériels et temps |
| **(Douanes)** | *(via Transitaire)* | *Géré par le transitaire -- pas un acteur direct du service Achat* |
| **Samuel** | IT Réseau | VPN Stormshield S2S |
| **Compta** | Finance | Paiement fournisseurs (BL + Facture + Packing list) -- Phase 2 |

---

## Les deux circuits distincts

### Circuit B -- Réappro (produit existant)
> Quotidien, volume élevé, données déjà disponibles -- **PRIORITAIRE**

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

### Circuit A1 -- Composants GDD (Général de Découpage) -- allégé
> Achat de composants pour l'usine GDD (molettes, ressorts, etc.)  
> **PAS de fiche achat** -- tout est déjà dans Sylob, référence déjà créée  
> La fiche achat template existe mais n'est jamais utilisée (produits trop différents entre eux) -- à traiter ultérieurement

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

### Circuit A2 -- Nouveau produit Chine (Import)
> Ponctuel, multi-service, processus long -- **Phase 2**

Workflow reconstitué depuis le board post-its équipe Achat :

```
SERVICE ACHAT
  Réception besoin nouveau produit → Négocier prix / Demander création référence
        │
        ▼ [CHARLES/ERIC/DAVID -- Commerce]    [DESIGN]
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

## Gaps identifiés -- board post-its équipe Achat (2026-06-03)

Éléments absents de notre modèle initial, découverts sur le board :

| Élément | Type | Impact BDD / Système |
|---------|------|----------------------|
| **Charles + David** | Acteurs Commerce (avec Eric) | Mettre à jour les blocs fiche achat |
| **Logistique** -- rôle clarifié | Acteur | Reçoit le planning de livraison d'Andréa pour anticiper (humains, matériels, temps) |
| ~~**Douanes**~~ | Supprimé | Géré par le transitaire, pas un acteur Achat direct |
| **Proforma** (contrôler + signer) | Document | Ajouter `doc_proforma` dans `achat.commande` |
| **PS signé** (Purchase Sheet) | Document | Notre fiche achat fournisseur -- à tracker |
| **Rapport d'analyses** (multiple étapes) | Étape processus | Table `analyse` distincte (labo qualité) |
| **Commande d'analyse** | Document | Lié à chaque checkpoint qualité |
| **MAT/SP** (Matière/Semi-produit) | Étape Circuit A1 | Spécifique usine GDD -- pas China import |
| **Validation boîte imprimée** | Étape Design | Checkpoint packaging |
| **Etiquettes + Shipping marks** | Données produit | Champs manquants dans `achat.produit` |
| **Planning livraison 1 semaine avant** | Alerte | À intégrer comme notification dans le dashboard |
| **ETD/ETA/Retard imprévu** géré par Transitaire | Info source | Transitaire = source de vérité ETD/ETA |

---

## Précisions process — Emmanuelle (2026-06-30)

> Corrections/validations recueillies avec Emmanuelle (Supply Chain).

- **Code article — pivot avancé** : Emmanuelle crée le code article **dès qu'on passe une commande fournisseur** (⚠️ correction : PAS en fin de flux à la réception comme dessiné en Circuit A2). Dès qu'il existe : **Clarisse** l'utilise pour l'artwork, **Andréa** pour la fiche achat. Le code article est donc le pivot amont du Circuit A.
- **Prérequis = gamme** : Emmanuelle a besoin de la **gamme** pour créer le code article → la gamme est le point de départ. Avant gamme/code = **prototype**.
  - **État actuel** : pas d'ID prototype formel. Le prototype est suivi dans **Gmail (côté TB)** et dans **BaseCamp (côté GDD)** — deux outils distincts, pas de référentiel unifié. ➜ **ACTION : creuser avec Olivier** (workflow proto GDD/BaseCamp).
  - ➜ **DÉCISION à prendre** : faut-il un **ID prototype unifié** (à réconcilier avec le « code provisoire `JJMMAAHHMM` » déjà prévu), porté du prototype jusqu'à l'attribution du code article Sylob (mapping conservé dans FUSEAU) ?
- **Circuit A1 élargi** : s'applique aussi à la **création de nouveaux composants (packaging)**, pas seulement aux composants GDD.
- **Validation des rapports d'analyse = Direction** (pas Emmanuelle).
- **Planning de livraison** (envoyé par Andréa) fan-out : **Logistique** (anticipe besoins humains / matériels / temps) **+ RH + Qualité** (fiche d'inspection).
- **Rôle Emmanuelle** = **Supply Chain & Data Analyst** (correction — pas Qualité).
- **Historique des prix : DÉJÀ dans le SI Sylob** → la fonction "historique prix" de FUSEAU fait doublon avec Sylob. Ne pas réinvestir dessus.
- ➜ **ACTION (au retour de congés d'Emmanuelle)** : auditer **tout ce que FUSEAU fait/stocke qui existe déjà dans Sylob** (candidats à supprimer/déléguer à Sylob), pour recentrer FUSEAU sur sa vraie valeur (suivi import maritime, artwork, suivi analyses, ingestion email-first).
- **Fiche achat = source de la nomenclature** : la fiche achat est créée à la **création de l'article** et **contient la nomenclature composant ET packaging**. Elle est maintenue à jour toute la vie de l'article via le **tableau Excel d'Andréa** (Excel → MAJ automatique de la fiche achat).
  - ➜ Réponse à « assez de données pour la nomenclature ? » = **OUI** (composant + packaging y sont).
  - ➜ Candidate directe pour combler le concept BI manquant n°2 « **Gammes & Sous-familles / nomenclature** ». Action : localiser + parser la structure de la fiche achat et documenter le lien **Excel Andréa → fiche achat**.

---

## Plan d'implémentation — captation des données Excel non-exploitées

> Issu de `docs/audit_excels_service_achat.md`. Chaque étape : table `achat.*` + transform + tests + dry-run → COMMIT + doc. ⚠️ **Avant chaque étape, vérifier ce qui existe déjà dans Sylob** (objectif cible = ramener la donnée dans Sylob, cf. directive transversale fiche achat).

| # | Source | Cible | Débloque | Effort | Statut |
|---|--------|-------|----------|--------|--------|
| 1 | `Matrice TB Import` (Lot-Vrac) | `achat.article_nomenclature` | Nomenclature composant+packaging, **Gammes & Sous-familles** (concept BI #2) | Faible | ✅ **FAIT 30/06 (1198 art.)** |
| 1b | `Matrice` (Lot Multiples, 122 col) | `article_nomenclature` (header, lot_vrac='Multiple') + `article_nomenclature_composant` (détail 1..8) | Nomenclature d'assemblage (ménagères/sets) | Moyen | ✅ **FAIT 02/07** (298 art. / 628 composants, copie figée mars — à rafraîchir) |
| 2 | ~~`Base article dimensions volume`~~ **Sylob V25 `af_article.sup_*`** (audit 02/07, pas d'Excel) | `achat.produit` (colonnes existantes, pas de nouvelle table) | Dimensions/volume/poids/EAN/PCB **officiels Sylob** | Faible | ✅ **FAIT 02/07** (`enrich_dimensions.py`, 1187/1198 art. enrichis) |
| 3 | `IMPORT`/`POINT MIF` | `achat.mif_suivi` | **BILAN MADE IN France** (lames envoyées/retour par lot PP) | Moyen (format pivot) | ✅ **FAIT 02/07** (16 lignes, copie figée mars — à rafraîchir) |
| 4 | `IMPORT`/`STOP REF CARREFOUR` | `achat.article_cycle_vie` | Cycle de vie / **Articles en sommeil** | Faible | ✅ **FAIT 02/07** (9 lignes, copie figée mars — à rafraîchir) |
| 5 | `IMPORT 2025` colonnes non mappées | étendre `commande` + `transform_commande` | OP/Client, Acompte, Alerte, Nb mois, **MAT/SP/Échantillon conformité** (lien qualité) | Faible-moyen | ✅ **FAIT 02/07** (636 lignes ; 8 colonnes ajoutées ; **bug corrigé** : `transitaire` lisait "Transport"=nom du navire au lieu de "Transitaire"=transporteur réel → nouvelle colonne `nom_navire` + `transitaire` fixé, `ot_transport` réupsertée) |
| 6 | PS remplies (PDF Drive) | croisement `article_nomenclature` | Validation par article (redondant si Matrice OK) | Élevé (OCR/parse) | Basse priorité |
| 7 | Drive TB/GDD (Inspection + Results of analysis) | `achat.qualite_doc` (index) + `achat.qualite_analyse` (mesures) | Lien FAIL→rapport (index) ; chrome (mesures) | Moyen (index) / Élevé (mesures, OCR) | ✅ **PILOTE 02/07** — index : 8 fichiers / 2 PO (`load_qualite_doc_drive.py`). Mesures chrome : 8/8 extraites via OCR (`load_qualite_analyse_ocr.py`) — **découverte** : les PDF SPECTRO n'ont aucune couche texte (0 caractère, 234 images/page), l'hypothèse "texte natif" du profil source était fausse. Pipeline : render 300dpi (pdfplumber) + tesseract, validé par recoupement (13.36% CA183435 = valeur de référence connue, 8 dates OCR strictement croissantes). `hardness_hrc`/`conformite` restent NULL (non fiables avec cet OCR généraliste, à ne pas deviner). Passage à l'échelle (~48 PO TB + GDD) : étendre `RECORDS` des deux scripts ou crawler le serveur `ANALYSES ET INSPECTIONS` directement en prod. |

**Transverse** : chaque champ ci-dessus doit être audité contre Sylob (table `tarrerias_production_dwh`) — cf. `docs/modele_semantique.md` (colonne « existe dans Sylob ? »).

---

## Suites pilote Drive qualité — arbitrages 02/07

> Décisions prises avec Antho suite au pilote OCR SPECTRO (item #7 ci-dessus).

1. **[FAIT 02/07 — code] Accès Drive en prod → API Google Drive (GCP)**, pas le connecteur MCP (session interactive uniquement, ne scale pas). Pas besoin de service account/domain-wide delegation : le client OAuth "Internal" du Plan A Gmail (déjà en place) peut porter un scope supplémentaire `drive.readonly` — réutilisation actée après audit (`src/utils/google_auth.py`, scopes partagés Gmail+Drive, un seul `token.json`). Script `src/scripts/etl/crawl_drive_qualite.py` créé : parcourt un dossier racine Drive (`DRIVE_QUALITE_ROOT_ID`) → dossiers PO → sous-dossiers `Inspection`/`Results of analysis` → PDF, parse `po_number`/`stade`/`ref_rapport`/`echantillon` par regex (dérivées du pilote manuel 8 fichiers), upsert `achat.qualite_doc` (réutilise le `load()` de `load_qualite_doc_drive.py`). **Reste à faire (actions non-délégables) : (a)** activer "Google Drive API" dans la console GCP du projet existant, **(b)** supprimer `config/token.json` et relancer un script pour re-consentir sur les 2 scopes, **(c)** renseigner `DRIVE_QUALITE_ROOT_ID` dans `config/.env`. Limite connue : `composant` (manche/tartineur/couperet...) n'est pas extrait automatiquement (texte libre trop variable) — reste NULL, contrairement au pilote manuel.
2. **[DEC] Priorité inversée sur l'extraction qualité** : ce qui compte réellement pour le service Achats, c'est la **décision finale conforme/non conforme**, pas la valeur brute du chrome (%). `cr_pct` reste utile en traçabilité mais n'est pas la donnée à exploiter en premier. → Si un budget OCR ciblé doit être investi, le prioriser sur le champ **`Conformity`** (case à cocher/image sur le rapport, cf. limite documentée dans `load_qualite_analyse_ocr.py`) plutôt que sur `hardness_hrc`.
3. **[DEC] Timing création code article — à valider avec le service Achats** : retour d'Emmanuelle — la demande de création de code article (par Design ou Commerce) arrive **assez tôt** dans le process réel (pas aussi tardive que schématisé en Circuit A2 §306). Pas perçu comme critique par Emmanuelle. **Action** : valider avec Andréa/Marlène **quelles données circulent déjà** au moment de cette demande (avant même la création du code article), pour vérifier si le modèle `achat.*` doit capter un état "pré-code-article" plus riche. Non urgent, mais à traiter avant le départ d'Andréa (31/07) si on veut son input.
4. **[FAIT — à planifier] Tesseract sur le poste de Marlène** : si le pipeline OCR SPECTRO doit tourner en routine (pas juste un pilote en session Claude), installer Tesseract OCR sur le poste qui exécutera `load_qualite_analyse_ocr.py` en prod. Ajouté à la checklist déploiement poste Marlène (cf. section dédiée ci-dessous).

---

## Décisions techniques arrêtées

| Décision | Choix |
|----------|-------|
| BDD cible | `dtpf_sylob_prod` schéma `achat` (Azure PostgreSQL) |
| Source DWH Sylob (POC) | `tarrerias_production_dwh` -- données brutes Sylob directes |
| Source DWH Sylob (prod) | `dtpf_sylob_prod` schéma `public` -- quand MyReport terminé + validation Emmanuelle |
| Clé primaire produit | Code article Sylob (créé par Emmanuelle) → EAN13 dans Sylob (clé de jointure vers `dtpf_sylob_prod` en prod) |
| Avant code article | Code provisoire `JJMMAAHHMM` |
| Interface | HTML statique → Streamlit si besoin d'écriture |
| Email | Gmail MCP -- email-first |
| Plugin | Cowork `.plugin` -- installable postes Andréa + Marlène |
| Secrets | Azure Key Vault via `DefaultAzureCredential` |
| Connection URL | `sqlalchemy.engine.URL.create()` -- gère les caractères spéciaux dans le mot de passe |

---

## Contraintes calendrier (Antho)

| Période | Type | Semaine | Impact projet |
|---------|------|---------|--------------|
| 01/07/2026 (1j) | HSNPM | S27 | Négligeable |
| 13-17/07/2026 | Formation DataScientest | S29 | ⚠️ Semaine bloquée -- tampon avant deadline 31/07 |
| **31/07/2026** | **Départ Andréa** | **S31** | **🔴 DEADLINE DURE -- validation POC avant cette date** |
| 07/08 + 10-14/08 | Formation DataScientest | S32-S33 | Post-POC |
| 17-31/08/2026 | CP | S34-S35 | Post-POC |
| 01/09/2026 (1j) | HSNPM | S36 | Post-POC |
| 28/09-02/10/2026 | CP | S40 | Post-POC |
| 24-31/12/2026 | CP | S52-S53 | Post-POC |
| Sept → Nov 2026 | Formation DataScientest (récurrent) | S37+ | Phases 3-4 à cadence réduite |

> Formation DataScientest = programme long (jusqu'en 2027). Prévoir ~1-2 jours/semaine bloqués post-POC.

---

## État d'avancement -- 2026-06-08

### ✅ Accompli (sessions 2026-06-03 → 2026-06-08)

| Livrable | Statut | Détail |
|---------|--------|--------|
| Cartographie des 4 sources de données | ✅ | `docs/cartographie_sources.md` |
| Profil complet des fichiers Excel Andréa | ✅ | `docs/profil_donnees.md` |
| ETL Python complet (extract + transform + load) | ✅ | `src/scripts/etl/` -- pipeline en prod |
| Structure projet aux standards TB Groupe | ✅ | `src/utils/`, `src/scripts/`, `config/` |
| Credentials Key Vault opérationnels | ✅ | `DefaultAzureCredential` → Key Vault → PostgreSQL |
| Connexion TCP PostgreSQL résolue | ✅ | `URL.create()` -- problème `@` dans le mot de passe |
| Cartographie DWH Sylob complète | ✅ | 3 sociétés, 16 modules, tables Achat/Article documentées |
| CREATE SCHEMA achat + chargement en prod | ✅ | 720 lignes commande, 1 198 produits |
| Enrichissement Sylob multi-schéma | ✅ | `enrich_from_sylob.py` -- cascade GDD → SE → CIE -- **99,7% couverture** (884/888 articles SE retrouvés) |
| Dashboard HTML Circuit B | ✅ | `dashboard_achats.html` -- KPIs, Chart.js, table filtrée, en cours, historique prix |
| Fix SyntaxError template dashboard | ✅ | `showTab` : adjacent string literals → `getAttribute` loop |
| Push GitHub | ✅ | `Antho-TB/Data-Achat` -- commit `60cbb51` |

### 🔴 Bloqué -- action requise (maj 2026-06-22)

| Blocage | Impact | Action |
|---------|--------|--------|
| **Lecture des PJ Gmail impossible** : `get_thread` renvoie noms + `attachment_ids` mais aucun outil ne télécharge le contenu | Parsing proforma/BL/PO PDF impossible → cœur du process email-first | POC : script Python `fetch_attachments` (Gmail API `attachments.get`, filtre label) → dépôt `\\Srv-files-pom\...\PJ\` → lecture disque. Cible : n8n Gmail trigger |
| Source transitaire `2026 SUIVI MARITIME.xlsx` (feuille `CONTENEUR PLEIN`) absente du périmètre partagé | ETD réel / ETA / Date livraison figés au cache Excel, jamais rafraîchis (233 #N/A légitimes/colonne) | Donner accès à `\\Srv-files-pom\...\SUIVI CDES IMPORT\2026\TRANSITAIRE\` + 2025 → ingérer dans `achat.ot_transport` |
| Autorisation lecture compte Gmail **Andréa** (Marlène = OK, plugin installé) | Phase 3 enrichissement | Confirmer accès au compte d'Andréa avant son départ 31/07 |

### 🟡 Non démarré

| Tâche | Phase | Priorité |
|-------|-------|---------|
| Validation schéma BDD avec Andréa + e.georgeon | Phase 1 | Haute |
| Analyse 2 fils Gmail Circuit B + 2 fils Circuit A bout en bout (avant départ Andréa) | Phase 1/2 | 🔥 Haute |
| Script `fetch_attachments` (PJ Gmail → disque) | Phase 3 | 🔥 Haute |
| Ingestion `2026 SUIVI MARITIME.xlsx` → `achat.ot_transport` | Phase 2 | Haute |
| Exploration `public` schema dtpf_sylob_prod (54 tables MyReport) | Prérequis prod | Moyenne |
| Streamlit si besoin d'écriture (signalement retard, notes) | Phase 2 | Basse |

### ✅ Fait depuis le 08/06 (corrige l'état figé ci-dessus)

| Livrable | Statut |
|---------|--------|
| Bascule dashboard HTML statique → **API FastAPI + frontend** (projet baptisé **FUSEAU**) | ✅ commit `54d22ac` |
| Kit déploiement poste Marlène (`platform_team`, X-API-Key, `marlene.env`) | ✅ |
| Modèle de données v0.2 (ADR `achat.commande_annotation`, `v_retard_article`, artwork 734 articles) | ✅ |
| **Plugin Cowork installé** (skills `achat-gmail-dwh`, `achatanalyser-mail`, `achatcircuit-a/b`, `achatsuivi-commande`, `achathistorique-prix`) | ✅ poste Marlène |

---

## État d'avancement -- 2026-06-30 (session FUSEAU)

> Reverse des sessions 25/06 → 30/06, jusque-là suivies dans `TASKS.md`.
> ⚙️ **Tâches opérationnelles courantes : voir `TASKS.md` (source vivante).** Ce plan = vue stratégique (phases, jalons, circuits).

### ✅ Fait depuis le 23/06

| Livrable | Détail |
|---------|--------|
| Déploiement poste Marlène | Terminé 29/06. `/api/health` → `write_enabled:true`, DWH connecté. |
| Gmail Plan A prouvé **bout-en-bout** | `BL-SZSE2606480` → PO 00017281/00017639, conteneur TGBU2004021, ETD 05/06. 23 PDF QUALITAIR téléchargés. OAuth + filtrage `--query` expéditeur (le label Gmail ne s'applique pas). |
| Contrainte `uq_commande_po_article UNIQUE (po_number, code_article)` | ✅ **déjà en prod** (vérifiée psql 30/06). Le « bloquant à créer » des notes précédentes était **périmé**. |
| Fix lignes de frais sans REF | `code_article` NULL (molding fee MEN 25081) échappait à la contrainte (NULL distinct en Postgres). → code synthétique `FRAIS-<slug(designation)>`. UPDATE prod 3 lignes (id 634-636) + patch `transform_commande` (full-refresh idempotent). |
| Git réconcilié | merge `origin/main` (commit Marlène) + push 30/06. |
| Plugin Cowork `dwh-achat` | postgres-mcp read-only (lecture DWH depuis Cowork). |
| Dette env | Décision : venv Python 3.11 sur les 2 postes + bump `SQLAlchemy>=2.0.36,<2.1` ; migration vers `uv`. |

### ✅ Décision actée (30/06) -- write-path Gmail = pattern A (zone découplée)

Contexte : `achat.commande` est full-refresh (TRUNCATE+INSERT). Coupler l'enrichissement Gmail à cette table = fragile, surtout que la **source de base va migrer Excel → DWH Sylob V25** (voir infra ci-dessous). Décision :

- Gmail (BL : `n_conteneur, n_bl, etd_reel, eta, transitaire`) → **UPSERT `achat.ot_transport`** (PK `n_conteneur`, déjà upsert, survit au full-refresh). `source_fichier='gmail'`. Jamais d'INSERT/UPDATE direct dans `achat.commande`.
- Lecture : `v_previsionnel` + `v_retard_article` font un `LEFT JOIN ot_transport` et `COALESCE(ot.etd_reel, c.etd_reel)` / `COALESCE(ot.eta, c.eta)` → **BL/maritime prioritaire** (décision source de vérité 30/06).
- Split : `etd_confirme` (niveau ordre) reste côté `commande` ; `etd_reel`/`eta` (expédition) = zone `ot_transport`.
- `apply_etd_eta.py` repointé vers `ot_transport` ; snippet `SKILL.md` réécrit (suppr. INSERT commande + colonne `source` fantôme → `source_fichier`).

Statut : implémentation en cours (code repo + `CREATE OR REPLACE` des 2 vues). ADR à classer dans `decisions_log/`.

### 🆕 Infra -- nouveau DWH Sylob V25 (dispo 30/06, cible source de vérité)

- Serveur `SRV-ERP-DATA` **192.168.102.41:5432** (≠ ancien on-prem `192.168.102.21:**5433**`), PostgreSQL 16, DB `tarrerias_production_dwh`, user `dataviz-admin` (même mdp que l'actuel). VPN Stormshield requis.
- ETL perso (Guillaume) : **Enseigne, Gamme, mappings client/centrale** livrés sur SE (`tarrerias_se_tarrerias_bonjean`) — 2 des 8 concepts manquants comblés ; GDD/CIE à suivre.
- Impact Data-Achat : future source des lignes `achat.commande` (remplace l'IMPORT Excel transitoire). Le pattern A garantit que l'enrichissement Gmail survit à cette bascule.

---

## Phases

### Phase 0 -- Initialisation ✅ (S23, 2026-06-08)

- [x] **Débloquer CREATE SCHEMA** -- résolu
- [x] ETL pipeline en prod -- 720 commandes, 1 198 produits chargés
- [x] Enrichissement Sylob 3 schémas -- 99,7% couverture
- [ ] Analyser 2 fils Gmail Circuit B bout en bout → `process_map_reappro.md`
- [ ] Valider schéma BDD avec Andréa + e.georgeon

### Phase 1 -- Circuit B opérationnel ✅ (livré S23, 2 sem. d'avance)

- [x] Lancer `python -m src.scripts.etl.pipeline` en prod
- [x] Explorer `tarrerias_production_dwh` -- 3 schémas Article, jointure Sylob
- [x] Croiser données Excel Andréa ↔ données Sylob
- [x] Dashboard HTML v1 : KPIs + Chart.js + table filtrée + en cours + historique prix

**Livrable** : `dashboard_achats.html` -- standalone, utilisable sans installation  
**Prochaine étape** : présentation à Andréa + Marlène le 09/06 → itérations sur retours

### Phase 2 -- Circuit A + Plugin Cowork (S26-S27, avant 01/07)

> ⚠️ S29 (13-17/07) = formation DataScientest -- terminer la phase 2 avant.

- [ ] Analyser 2 fils Gmail Circuit A → `process_map_nouveau_produit.md`
- [ ] Fiche produit collaborative (5 blocs, code provisoire JJMMAAHHMM, photos)
- [ ] Plugin Cowork v0 (skills : nouveau-produit, remplir-bloc, analyser-mail, suivi-commande, historique-prix, verif-doc)

### Phase 3 -- Intégration Gmail & cohérence (S30, avant 31/07)

> S29 (13-17/07) = formation DataScientest (semaine bloquée).  
> **Andréa absente à partir du 31/07 -- deadline dure pour la validation.**  
> Phase 3 doit être livrée S30 (20-26/07) pour laisser S31 à la validation.

- [ ] Connecter MCP Gmail (Andréa + Marlène)
- [ ] Parser fils de discussion → enrichir BDD produit
- [ ] Rapport cohérence mail ↔ BDD (incohérences prix, quantités)

### Phase 4 -- Vérification documentaire & Paiement (S37+, après 01/09)

- [ ] Comparaison facture fournisseur vs commande Sylob
- [ ] Checklist réglementaire (affichage France/EU, douanes, conteneurs)
- [ ] Interface Compta : BL + packing list + bon réception → validation paiement

---

## Jalons

| Jalon | Semaine | Livrable | Statut |
|-------|---------|---------|--------|
| J0 -- Schema `achat` créé + ETL en prod | S23 (08/06) | Premier chargement réel DB | ✅ |
| J1 -- Dashboard HTML + données Sylob croisées | S23 (08/06) | `dashboard_achats.html` v1 | ✅ **2 sem. d'avance** |
| J2 -- Validation métier + process map Circuit B | S24 (15/06) | Retours Andréa/Marlène + `process_map_reappro.md` | 🔜 Mardi 09/06 |
| J3 -- Process map Circuit A validé | S26 (26/06) | `process_map_nouveau_produit.md` | ⏳ |
| J4 -- Plugin Cowork v0 | S28 (10/07) | 3 skills opérationnels | ⏳ -- doit être fini avant S29 FORM |
| J5 -- Intégration Gmail | S30 (24/07) | Cohérence mail ↔ BDD | ⏳ -- après S29 FORM |
| **Deadline POC -- Andréa part le 31/07** | **31/07/2026 (S31)** | **Validation métier** | ⏳ -- deadline dure, Andréa absente après |
