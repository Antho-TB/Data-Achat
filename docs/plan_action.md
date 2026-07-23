# Plan d'action -- Système Data-Achat TB Groupe

> Issu de la réunion de cadrage · 2026-06-01  
> Mis à jour : **2026-07-23** (tache planifiee Windows + acces LAN Andrea pour la mise en prod du **mardi 28/07** ; voir commit `6751c07`). Le detail des decisions metier en attente est dans la section **"Retours demo 21/07 14h"** juste en dessous -- c'est la liste vivante, pas la section OAuth (obsolete, Antigravity abandonne).  
> Périmètre : Achats Import · Utilisateurs finaux : Andréa, Marlène, Olivier, Eric, Charles, David, Jonatan, Julia, Emmanuelle

---

## Session 20/07 — récap

- **Correction calcul retard déployée en prod** : `sql/20260720_fix_calcul_retard.sql` joué (3 vues : `v_retard_expedition` figé grain ligne, `v_retard_fournisseur` moyenne 12 mois glissants, `v_retard_article` corrigée) + `app/main.py` repointé. Définition métier 07/07 : `retard = ETD réel − ETD confirmé`, avances planchées à 0, deux axes séparés (KPI figé vs flag opérationnel). ⚠️ **KPI à investiguer** : sortie suspecte (quasi 100% des lignes « en retard », WANXIN 182j) → creuser ce que représente `etd_confirme` vs `etd_reel` dans la donnée + effet du grain PO×article.
- **Suivi maritime chargé en prod** : `SUIVI MARITIME TARRERIAS 2026.xlsx` (fichier transitaire QUALITAIR, Drive, frais 17/07) → `transform_maritime` (46 conteneurs) → `load_ot_gmail` COMMIT. `achat.ot_transport` : 87 → 90. **Bug rollover corrigé** dans `transform_maritime.py` (garde-fou : si ETD réel > ETA, recule d'un an — cas cellules datetime ISO à année absolue erronée).
- **Archi pérennisation tranchée** (bus factor / départ Andréa 31/07) : pipeline sur infra + comptes non-nominatifs, jamais un poste/compte humain.
  - **Compte de service AD** `svc-dataachat` (nom à valider Sam) : lecture récursive `\\Srv-files-pom\partage\ADA\METIER\SUIVI CDES IMPORT\` (couvre `2026\` IMPORT/TRANSITAIRE/ANALYSES ET INSPECTIONS + `PRODUITS\` Matrice/dimensions) + « log on as batch job » sur hôte LAN (candidat n8n `192.168.102.36`). **Ticket GLPI envoyé le 20/07.**
  - **PostgreSQL** : login de service `dtpf_sylob_dataachat_prod` (modèle `dtpf_sylob_myreport_prod`) membre de `platform_team` ; **basculer l'ownership de tous les objets `achat.*`** (17 tables/6 vues/7 séquences, aujourd'hui owned par le login perso `dtpf_sylob_anthony_bezille_prod`) vers `platform_team`. ⚠️ Le login perso n'est PAS membre de `platform_team` (membre de `group_dtpf_sylob_admin_prod` seulement) → REASSIGN à faire avec l'identité admin Entra/`azure_pg_admin`.
  - Secrets via Key Vault `kv-dtpf-prod` (`psql-prod-sylob-dataachat-login`/`-password`) ; SP `sp-client-id` pour le mode secretless.
- **Cartographie sources verrouillée** (mail Andréa 25/06 + Zoom 07/05) : SMB = tout sous `SUIVI CDES IMPORT\` (IMPORT, TRANSITAIRE, ANALYSES ET INSPECTIONS\4.INSPECTIONS, PRODUITS) ; Drive/Sheets API = Artwork (`LIS-CON-28`), Suivi analyses (`SUIVI DES ANALYSES`), qualité crawl (`DRIVE_QUALITE_ROOT_ID`). Direction actée : **API Google Sheets pour les gsheets natives, zéro doublon** (à implémenter : scope `spreadsheets.readonly` + `src/utils/gsheets.py`).
- **Board Point IT recalé** (data table Zoom) : parent Data-Achat 65→80%, ETL Gmail 60→70%, FUSEAU 80→85% ; 5 sous-lignes ajoutées (Démo 07/07 Done, Captation Excel Done, Correction retard Done, Branchement sources Andréa OnGoing 40%, Pérennisation infra OnGoing 20%).
- **Correction mémoire** : rôles inversés — **Marlène MONTBRIZON = Responsable Achats** (reste), **Andréa JAMET = Assistante Achats** (part le 31/07).

---

## Session 21/07 -- récap

- **Design System TB applique** (`ffaf7de`) : tokens couleur/typo remappes dans `frontend/index.html` (monochrome + rouge signal + bleu profond, Archivo/Roboto/Roboto Mono, radius 0). Reste : teintes tertiaires en dur (badges, zebra table, header).
- **Bug artwork "Valide = 0/792" corrige definitivement** (`aed9ab5`, `feec5b5`) : 3 bugs empiles, pas un seul.
  1. `parse_fr_date()` ne gerait pas le format ISO pandas/openpyxl (cellules Excel typees date).
  2. `_read_rows()` ne lisait que le 1er onglet du gsheet source (le fichier a 2 onglets distincts, pas 2 blocs empiles dans une seule feuille) -- le 2e onglet ("Liste artworks", 465 lignes, la quasi-totalite des articles reels) etait ignore en silence.
  3. `/api/artwork` et le KPI Dashboard lisaient la table brute `achat.artwork` (jamais au courant du statut de validation design) au lieu de la vue `achat.v_artwork` qui fusionne `achat.artwork_statut` -- la vue existait deja mais rien ne l'utilisait.
  Backfill complet relance (gsheet recupere via connecteur Drive) : `achat.artwork_statut` = 384 lignes (380 Valide, 4 Nouveau). `artwork_valides` API : 284 -> 374/792 (chiffre reel).
- **Bug ETD/ETA "Prochaines arrivees" retire** (`aa37b21`) : code mort backend (la vue avait deja ete remplacee par l'onglet Conteneurs, qui distingue correctement ETD/ETA/Livraison).
- **Qualite** (`1ee472a`, `b8afdc6`, `2d293e0`) : lien Drive + conformite labo sur N° inspection, filtre par reference article, infobulles sur toutes les colonnes.
- **Dashboard** (`17b3605`) : statut "Inconnu" et "Deja livre" rendus visibles (2 KPI + camembert 4 tranches) -- avant, ces lignes disparaissaient silencieusement des compteurs En retard/Dans les delais.
- **Suivi commande** (`19207c3`) : badge parti/pas-parti (rouge/bleu) au lieu d'un texte discret.
- **Audit retours metier reorganise** en 4 blocs (semantique a arbitrer, donnees manquantes a la source, constructions substantielles non demarrees, a revalider a l'ecran) -- `docs/20260721_FUSEAU_Audit_RetoursMetier_v1.md`.
- **Passation Antigravity mise a jour** (`bbf1ac2`) -- `05_ARCHIVES/Versions_Anterieures/20260721_Passation_Antigravity_v1.md` (archivee : Antigravity abandonne, Claude code directement en sandbox depuis), inclut l'etat exact de l'OAuth Drive (prerequis restants, qui doit faire quoi).
- Tout est commite et pousse sur `main` jusqu'a `bbf1ac2`.

---

## Retours démo 21/07 14h — tâches à faire

> Récupérés en direct pendant/après la démo métier. Détail complet et argumenté : `docs/20260721_FUSEAU_RetoursDemo14h_v1.md`. Légende : [QW] quick win · [M] touche modèle/intégration · [DEC] décision métier requise.

### ✅ Déjà traité en session (21/07 après-midi)
- [x] [QW] Suivi commande — filtre cassé (`f-po`/`f-designation` absents du DOM, cassait TOUS les filtres).
- [x] [QW] Historique de prix — recherche par désignation (Fournisseurs > Détail + onglet Article).
- [x] [QW] Précision des prix : 2 → 3 décimales partout.
- [x] [M] KPI Retards : graphique + tableau fournisseurs passés en **retard maxi constaté (jours)** au lieu du nb d'articles, avec unité et tooltip méthodo.
- [x] [QW] Suivi commande — tooltip "Dernier évènement" avec le détail réel (champ modifié ou statut logistique atteint).
- [x] [QW] Artwork — tooltip natif sur la cellule Commentaire tronquée.
- [x] [M] Artwork — écart `artwork_en_attente` (KPI=1 vs 8-9 lignes gsheet) corrigé : code provisoire `NOUVEAU-<slug>` pour les lignes "PAS DE REF" + ligne fantôme `achat.artwork` pour les rendre visibles dans `v_artwork`. Effet de bord positif : ~153 articles jamais commandés redevenus visibles (`artwork_total` 792→951).

### 🔬 Anomalie à vérifier (pas encore corrigée)
- [ ] **WANXIN : retard maxi = 444 jours** — chiffre hors norme, probablement une donnée ETD confirmé mal saisie plutôt qu'un vrai retard. `nb_articles_en_retard` = 0 (pas un cas actif) mais à vérifier avant de le citer en démo.

### 🟡 Décisions métier requises avant dev (deadline Andréa 31/07)
- [ ] [DEC] **Statut "Livrée"** : rapprocher avec Sylob (réceptionné/entrée en stock) + afficher la Conformité/Non-conformité Qualité à réception. Reste à identifier : quelle table Sylob porte la date de réception réelle par PO/article ?
- [ ] [DEC][M] **Raison du retard** : à extraire du corps des mails (parsing), pas de saisie structurée existante — rejoint le chantier "non-conformité par mail" déjà identifié.
- [ ] [DEC] **Doublons fournisseurs — revirement** : GUANGWEI/DIAMOND TRACK et SMART IRON/JIT GLOBAL signalés aujourd'hui comme de vrais doublons à corriger via l'ID Sylob `frn_code` (pas le nom texte) — **contredit la décision actée le 25/06** ("comportement correct, rien à corriger"). À auditer (`enrich_ca.py`/`enrich_from_sylob.py`) et retrancher avec le métier avant de coder.
- [ ] [DEC] **Qualité — code article absent des rapports d'inspection** : proposition = le service Qualité nomme désormais les PDF avec le code article dedans. Pas un dev FUSEAU, une évolution de process côté Qualité à valider avec eux.
- [ ] [DEC] **Promo/Opé — filtre trop large** : ne garder que ce qui commence par **OP** ou **NOUVEAU** + champ **PRIORITAIRE (Oui/Non)** séparé du filtre texte. Nécessite un point avec Andréa/Marlène sur la définition de "prioritaire".
- [ ] [DEC] **Fiche Achat / Article — sources de vérité à retrancher** : EAN/PCB → Sylob source de vérité ; le reste (marquage, matière, packaging détaillé) → fiche achat existante tant qu'elle n'est pas remplacée. Onglet Article = vue 360° (Sylob + Matrice + Fiche Achat), pas juste l'historique prix. Onglet Fiche Achat = **consultation des fiches existantes + génération PDF + mise à jour**, pas la création ex nihilo cadrée initialement. → change le périmètre des deux onglets tels que conçus aujourd'hui.

### ⬜ Chantiers à planifier (scope clair, pas encore démarrés)
- [ ] Suivi commande : différencier **statut de paiement** (payé/non payé) de l'**état de la commande** (conflaté aujourd'hui dans `statut`).
- [ ] Prévisionnel : vue prioritaire **par livraison/conteneur/mois** ; B/L en attente ou bloqués groupés par conteneur puis fournisseur ; vue "déjà payé" par fournisseur ET conteneur/BL ; alertes changement ETA remontées au Dashboard (mise en forme progressive orange→rouge→violet selon nb de changements).
- [ ] Qualité : brancher le parsing numéro de rapport → code article une fois la convention actée avec le service Qualité (cf. [DEC] ci-dessus).
- [ ] Article : colonne **"Artwork (Oui/Non)"** (jointure `achat.v_artwork`).
- [ ] Fiche Achat (aperçu live construit cette session) : emplacement du marquage (zone produit), bloc légal AGEC intégral, N° commande + N° lot, HO Code (optionnel, distributeurs type Carrefour), clarifier Name (Sylob EN) vs Désignation FR, vrai logo Design System (asset au lieu du bloc texte "TB").
- [ ] Artwork : coller aux noms de colonnes/formats de date du gsheet source `LIS-CON-28-0` ; permettre l'ajout de nouvelles lignes depuis FUSEAU (écrire dans `artwork_statut`, pas juste consulter) ; aperçu + lien cliquable vers le document Drive par ligne.
- [ ] Transverse : extractions régulières (gsheet/Excel/PDF) au lieu d'exports manuels ponctuels ; passe de vérification systématique Sylob (article/fournisseur/EAN) au-delà du ponctuel du 02/07.

**Priorité suggérée** : trancher les 6 points 🟡 avec Andréa/Marlène avant le 31/07 — en particulier doublons fournisseurs et sources de vérité Fiche Achat/Article, qui changent le périmètre de ce qui est déjà construit. Les chantiers ⬜ sont non bloquants pour le 31/07.

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

## Décisions actées en démo — 07/07 (14h, équipe métier)

> Compte-rendu du questionnaire d'entretien (`docs/20260707_questionnaire_demo.md`,
> 22 questions). Décisions actées + actions techniques qui en découlent.

### Qualité / conformité
- **Conforme = validé implicitement ; non conforme = décision d'Eric T (Commerce) par mail.** Asymétrie à gérer : pas de signal positif systématique, seulement un signal de rejet.
  → **Action [M]** : parser le corps des mails (boîte Eric T) pour détecter les rejets, plutôt que d'étendre l'OCR SPECTRO sur `conformite` (le champ n'est de toute façon pas dans le PDF). À rapprocher du Plan A Gmail existant (`fetch_attachments.py`).
- **GDD = circuit qualité distinct**, moins formalisé que TB. Ne pas généraliser `crawl_drive_qualite.py` à GDD avec la même logique — traiter séparément, priorité basse.
- **`hardness_hrc` NULL = normal**, confirmé : test de dureté fait uniquement sur les couteaux, jamais sur semi-produits/couverts. Rien à corriger sur le pilote OCR SPECTRO.

### Historique prix
- **Décision : former l'équipe sur Sylob natif plutôt que maintenir "Historique prix" côté FUSEAU.** Ne pas prioriser de nouveaux développements sur cette fonctionnalité (le fix désignation du 07/07 reste utile en transition).

### Suivi commandes — retards
- **UI/UX de la distinction "(parti)"/"(pas parti)" à revoir** — le fond est bon, la présentation non.
  → **Action [QW/UI]** : retravailler l'affichage (pas juste un `<small>` à côté du badge).
- **⚠️ Calcul du retard à corriger.** Définition validée : `retard = ETD réel − ETD confirmé`, moyenne **par fournisseur, par an, sur 12 mois glissants**, **figée à l'ETD** (pas recalculée en continu). Ce n'est PAS `date_livraison − ETD` comme documenté précédemment.
  → **Action [M] prioritaire** : auditer et corriger `v_retard_article` (et toute vue/requête dérivée) pour appliquer cette définition exacte avant la prochaine démo.
  → ✅ **CODÉ 20/07** — migration `sql/20260720_fix_calcul_retard.sql` (3 vues : `v_retard_expedition` figé grain ligne + `v_retard_fournisseur` moyenne 12 mois glissants + `v_retard_article` corrigée) + `app/main.py` repointé sur `v_retard_fournisseur`. **Reste : jouer le SQL sous VPN + relancer l'API** (cf. `TASKS.md`). Décisions 20/07 : deux axes séparés (KPI figé vs flag opérationnel), avances planchées à 0.
- Édition du commentaire retard : **aucune restriction de rôle** à implémenter (tous les comptes authentifiés).

### Code article / prototype (Circuit A)
- La demande de code article démarre **très tôt, via des échanges Gmail informels (boîte Eric T)**, pas une demande formelle.
- **Problème structurel identifié : relation plusieurs-à-plusieurs** entre prototypes/conversations et code article.
  → **Action** : explorer la structure du **"code affaire" dans la BDD GDD** comme précédent/modèle possible pour l'ID prototype unifié, avant la discussion avec Olivier.
- Q11 (données circulant avant le code article) et Q12 (ID prototype unifié) : **non tranchées**, à reposer.

### Paiement / conteneur (validé GO, à planifier)
- Paiement = **liasse documentaire BL + facture + packing list** (pas le BL seul) → modèle de données doit lier les 3.
- Flag promo/urgence : posé **à la commande OU en milieu de circuit** (vente commerce) → champ modifiable à plusieurs étapes, pas figé à la création.
- Règle de retard de paiement : **ETD_BL + 15 jours de tolérance**, retard compté seulement au-delà.
  → **Action [M]** : ces 3 règles à implémenter ensemble dans le futur module paiement/conteneur (post-démo, effort [M] déjà estimé le 25/06).

### Nouveaux onglets — validés, périmètre cadré
- **Article** : suivi du changement de fournisseur dans le temps uniquement — stock/cycle de vie = Supply Chain, **hors périmètre Achats**.
- **Promo** : périmètre large validé ("oui pour tout" : fidélité, promo ponctuelle, nouveau client type COSTCO) — à détailler avec exemples concrets au design.

### Divers
- **GUANGWEI = DIAMOND TRACK, même fournisseur** — le CA cumulé partagé (double-attribution) est **correct**, pas un bug. Rien à corriger.
- **Tous les montants sont en USD**, toutes sources confondues — confirmé.

### Points non traités en démo (à relancer, cf. questionnaire §7)
- 🔴 **Accès Gmail boîte Andréa avant le 31/07** — reste LE point bloquant deadline, non traité en démo, à relancer en priorité absolue.
- Fraîcheur de l'IMPORT Excel (10/06) à vérifier avant validation finale.
- Accès réseau au dossier `2026 SUIVI MARITIME.xlsx` (transitaire) toujours en attente.

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
