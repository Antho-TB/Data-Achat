# FUSEAU : cadrage de la refonte de l'onglet Qualité (BUG-007)

> Rédigé le 05/10/2026. Cadrage en lecture seule : aucune modification de code, aucune écriture en base.
> Sources du besoin : notes d'Antho du 29/09, tableau de suivi de Marlène.
> Chiffres mesurés le 05/10/2026 sur `dtpf_sylob_prod` (schéma `achat`), le DWH Sylob `tarrerias_production_dwh` et le gsheet SUIVI DES ANALYSES (id `1lE9te1TlyBP1C5p3Axj9G-luc66A6ZGP-cJKdHJzi-c`).

## 1. Synthèse

| Constat | Chiffre | Conséquence |
|---|---|---|
| La commande d'analyse (CA) existe dans Sylob : commande d'achat SE vers le fournisseur `TARRERIAS ET CIE` (code 00000583), référence au format `<PO FRS>/<STADE>` | 1 692 CA depuis 2024, 94 % avec un n° de PO lisible | Sylob fait foi pour le n° de CA, le PO, le stade, la date d'envoi, le contenu et le montant |
| Le miroir Cie (commande de vente Cie vers SE) porte le n° de CA dans `commande_identifiant_edi` | 1 692 sur 1 692 | Jointure SE et Cie exacte, sans parsing |
| Le BL de la prestation est la livraison de vente Cie (`vue_livraison_vente.livraison_livraison`) | BL 6718, 6723, 6537 du gsheet retrouvés | Le n° de BL vient de Sylob |
| PO de `achat.commande` ayant au moins une CA | 119 sur 179, soit 66 % | Lot 1 faisable sans nouvelle table |
| Couples (PO, article) de `achat.qualite` dont une CA cite l'article en commentaire de ligne | 666 sur 956, soit 70 % | Grain PO x article x stade atteignable depuis Sylob |
| `achat.qualite_suivi` et `achat.qualite_facturation` | 0 ligne chacune | Tables créées le 30/06, jamais alimentées |
| Lien « FAIL vers rapport Drive » de l'écran actuel | 0 lien affiché | Jointure cassée (voir 2.4) |
| Formats de PO incompatibles entre tables | `qualite_decision` : 19 PO joints tels quels, 73 après normalisation | À corriger dans tout le lot 1 |

## 2. État actuel

### 2.1 Écran (`frontend/index.html`, `#tab-qualite`, `loadQualite()`)

Deux blocs :

1. **Évaluation fournisseurs (inspection / NCR)** : `/api/qualite/fournisseurs`, vue `achat.v_qualite_fournisseur` (taux FAIL, NCR, réceptions non conformes par fournisseur). À supprimer selon le métier.
2. **Suivi qualité par produit** : `/api/qualite`, 1 000 lignes max. Colonnes : PO, Article, Fournisseur, MAT, SP, Échant., BAT, Inspection (OK/FAIL + date), N° insp. (lien Drive), Conformité labo, Récep. (+ badge réception Sylob), NCR. Filtres : fournisseur, article, résultat d'inspection, « BAT » (Conforme / Non reçu).

Absents de l'écran : désignation, stade en tant que dimension, n° de CA, n° de BL, date d'envoi en analyse, suivi de facturation.

### 2.2 Endpoints (`app/main.py`)

| Endpoint | Source | Remarque |
|---|---|---|
| `GET /api/qualite` | `achat.qualite` + LATERAL `qualite_doc` (drive_url) + `qualite_analyse` (conformité) par `ref_rapport` | Filtres serveur fournisseur, résultat, article |
| `GET /api/qualite/fournisseurs` | `achat.v_qualite_fournisseur` | Bloc à supprimer |
| `GET /api/qualite/rapports` | `qualite_doc` + `qualite_analyse` joints à `commande` par `po_number` | Utilisé par la fiche article |

### 2.3 Tables

| Table | Grain | Alimentation | Lignes | Dernier chargement |
|---|---|---|---|---|
| `achat.qualite` | PO x article (UNIQUE) | ETL IMPORT, full-refresh (`transform_qualite`, `load_qualite`) | 956 (179 PO, 91 FAIL) | 05/10/2026 |
| `achat.qualite_doc` | fichier rapport | crawl Drive (`load_qualite_doc_drive.py`) | 248 (232 inspections sans `ref_rapport`, 16 analyses avec CA) | 05/10/2026 |
| `achat.qualite_analyse` | fichier rapport | OCR SPECTRO (`load_qualite_analyse_ocr.py`) | 8 (pilote) | 02/07/2026 |
| `achat.qualite_decision` | événement mail | pipeline Gmail | 364 (99 PO) | 05/10/2026 |
| `achat.qualite_suivi` | échantillon | aucun transform écrit | 0 | jamais |
| `achat.qualite_facturation` | CA facturée | aucun transform écrit | 0 | jamais |

Répartition de `qualite_decision` par stade : MAT 82, SP 58, BAT 66, réception 124, inspection 10, FRI 9 (conforme et non conforme confondus).

### 2.4 Défauts constatés en passant

| Défaut | Mesure | Effet |
|---|---|---|
| `achat.qualite.ref_rapport` porte la référence DEKRA (`4945056.00-28`), alors que `qualite_doc.ref_rapport` porte une CA (`CA189579`) et que les 232 inspections de `qualite_doc` n'ont pas de `ref_rapport` | 0 correspondance | La colonne N° insp. n'affiche jamais de lien Drive |
| `achat.commande.po_number` est sans zéros de tête (6 chiffres), `qualite_doc` et la majorité de `qualite_decision` sont sur 8 chiffres | `qualite_doc` : 0 PO joint tel quel, 43 sur 44 après `lpad(…, 8, '0')` | `/api/qualite/rapports` par PO et tout futur croisement ratent silencieusement |
| `achat.commande` contient 5 PO à 1 chiffre (`1` à `5`) | 5 | Bruit de saisie IMPORT, à exclure des taux |

## 3. Sources

### 3.1 IMPORT (fichier Excel d'Andréa, onglet `IMPORT 2026`)

Le bloc « Analyses échantillons et inspections » (en-tête de groupe ligne 3 à fond marron, thème 9 teinté) couvre les colonnes AA à AH. Lecture : `extract_import()` (`header=3`), puis `transform_qualite()` qui mappe :

| Colonne IMPORT | Colonne `achat.qualite` | Valeurs observées (copie locale du 20/07, 900 lignes) |
|---|---|---|
| AA Matière (MAT) | `matiere` | Conforme 526, Aucune 210, Non reçu 164 |
| AB Semi-production (SP) | `semi_production` | Aucune 477, Conforme 236, Non reçu 184, Non conforme 1, variantes « Conforme couteau » |
| AC Échantillon de conformité | `echantillon_conformite` | Validé 660, Aucune 33, « / » 13 |
| AD Production (BAT) | `production_bat` | Conforme 662, Non reçu 195, Aucune 41, Non conforme 1 |
| AE Date inspection | `date_inspection` | dates ou plages texte (`19-21/07/2026`) |
| AF Rapport d'inspection | `resultat_inspection` + `ref_rapport` | `OK 4956124.00-7`, `FAIL 4940165.00-18` |
| AG Réception (RECEP) | `reception` | Conforme 116, Aucune 34, Non conforme 1 |
| AH Non-conformité (NCR) | `ncr` | `NCR 00000405`… |

`_clean_checkpoint()` ramène « Aucune », « / » et vide à NULL.

Écart avec le besoin : le métier attend les valeurs **en cours, conforme, FAIL, réception**. L'IMPORT ne porte que Conforme / Non reçu / Non conforme. « Non reçu » correspond probablement à « en cours » ; « FAIL » n'existe que dans le rapport d'inspection (AF), pas par stade. 51 cellules sont surlignées en rouge (`FFC00000`) sur MAT, SP et BAT : signal visuel non capté par l'ETL, à faire expliquer.

Aucune date d'envoi en analyse n'est présente dans l'IMPORT (ni colonne, ni commentaire de cellule).

### 3.2 Gsheet SUIVI DES ANALYSES

Lu le 05/10 via le connecteur Drive. Le classeur a changé depuis le profil du 30/06 (6 blocs empilés sur une feuille) : il compte désormais **4 onglets**.

| Onglet | Plage | Colonnes |
|---|---|---|
| ANALYSES EN ATTENTE | A1:P198 | Ref, Désignation échantillon, Stade Echantillon, PO FRS, CA, Date d'envoi, N° BL, Niveau d'urgence 1 à 5, Etat du produit, Etat analyse (Katlyne/Florian/Marie) ; légende en L:P |
| FACTURATION INTERSITE | A1:Z599 | Stade sample, PO fournisseur, CA, S, D, M, C 10, C10-50, C+50, R, Montant HT CA, Date de BL, BL, puis S à R répétés côté BL, Montant HT BL, A facturer, Facturation faite ; grille de prix en Y:Z |
| LISTE DES REFERENCES | A1:B540 | Référence, Désignation |
| ARCHIVES DES ANALYSES | A1:I1792 | REF, Désignation échantillon, Stade Echantillon, PO fournisseur, CA, Date d'envoi de la CA, N° BL, Opérateur, Date de BL |

Lecture dans le repo : aucune. L'id n'apparaît que dans les archives (`05_ARCHIVES/…/profil_suivi_analyses.md`, `20260722_TASKS_avant_fusion.md`). `docs/sources_gsheet_drive.md` et `docs/modele_semantique.md` décrivent l'ancien découpage en blocs ; `modele_semantique.md` annonce « 95 lignes récupérées », la base en contient 0.

Points notables :
- Le **CA du gsheet est le n° de commande d'achat SE dans Sylob** (`00190050`, `00190051`, `00190320` vérifiés) ; le `CA189579` de `qualite_doc` est le même identifiant préfixé.
- Les colonnes S, D, M, C, R correspondent aux articles prestation Sylob : `Pres0002` ANALYSE SPECTRO, `Pres0003` DURETE, `Pres0038`/`Pres0007` TEST MECANIQUE, `Pres0016` TEST LAVE VAISSELLE +50 CYCLES, `Pres0013` REDACTION D'UN RAPPORT. Les prix de la grille (21,31 ; 7,40 ; 10,94…) sont ceux des lignes Sylob.
- La paire « côté CA » / « côté BL » de FACTURATION INTERSITE sert à comparer le commandé et le livré, puis à cocher la facturation. C'est la partie que Sylob ne garantit pas.
- « Etat analyse » est vide sur l'échantillon lu : le résultat d'analyse n'est pas tenu dans ce classeur.
- Gotchas confirmés : `#N/A` de bas de tableau, PO multiples (`173654-177438`), zéros de tête variables (`176529` contre `00187132`).

### 3.3 Sylob : la commande d'analyse inter-société

Chaîne observée sur l'exemple du PO fournisseur `00187132` (JIT GLOBAL, 103 102 USD HT, créé le 13/08/2026) :

| Étape | Sylob | Clé | Exemple |
|---|---|---|---|
| Commande fournisseur | SE Achat `vue_commande_achat` | `commande_numero_de_la_commande` | `00187132`, réf. `APPRO 260731` |
| CA (prestation qualité) | SE Achat `vue_commande_achat`, `frn_raison_sociale = 'TARRERIAS ET CIE'` | `commande_reference` = `PO/STADE` | `00190050`, réf. `00187132/BAT`, 68,36 € HT, créée le 29/09 |
| Lignes de la CA | SE Achat `vue_commande_achat_detail` | `article_code_article` = `PresXXXX`, `ligne_commentaire` = ref + désignation de l'échantillon | `Pres0002` x2 « 10340037 TARTINEUR BOIS CLAIR CRF », `Pres0003` x2, `Pres0013` x1 |
| Miroir côté Cie | Cie Vente `vue_commande_vente`, client SE TARRERIAS BONJEAN | `commande_identifiant_edi` = n° de CA | `00007441`, réf. `00187132/BAT`, 68,36 € |
| BL de la prestation | Cie Vente `vue_livraison_vente` | `livraison_livraison`, `livraison_reference` = `PO/STADE` | BL `00006718`, réf. `00176529/BAT`, 403,70 € (= gsheet CA 179939) |
| États | `commande_etat_de_reception`, `commande_etat_de_facturation` (SE) ; `livraison_etat_de_facturation` (Cie) | | CA 2026 : 489 reçues et facturées, 11 reçues non facturées, 12 ni l'un ni l'autre |

Attention : la Cie Vente porte aussi des commandes saisies à la main avec des références libres (`MAT / 00187132`, `SP 00187132`, `00187132 / SP`). Le côté SE Achat est plus régulier ; c'est lui qu'il faut lire, et passer par `identifiant_edi` pour rejoindre la Cie.

Qualité du parsing de `commande_reference` (1 692 CA SE vers Cie depuis le 01/01/2024) :

| Mesure | Valeur |
|---|---|
| Référence contenant un n° de PO (5 à 8 chiffres) | 1 592 (94 %) |
| Référence multi-PO (`173654-177438`, `PLUSIEURS PO`) | 159 |
| Stade extrait | BAT 735, RECEP 348, SP 251, MAT 248, non reconnu 110 |
| Variantes de stade à normaliser | RECEPTION, RECE, recep, SEMI PROD, MATIERE, SPBAT, `19108RECEP`, `PO76356/…` |
| Autres achats chez Cie mélangés (outillage `Outi…`, `POLYFLAME`, `SGS`, `TEST MECA`) | quelques dizaines, à filtrer sur les articles `Pres%` |
| Lignes de CA citant une ref article 8 chiffres en commentaire | 1 231 CA sur 1 692 |
| CA de `qualite_doc` retrouvées dans Sylob | 5 sur 5 |

Taux de rapprochement avec FUSEAU :

| Mesure | Valeur |
|---|---|
| PO numériques de `achat.commande` | 179 |
| dont avec au moins une CA | 119 (66 %) |
| par stade : BAT / MAT / SP / RECEP | 109 / 89 / 78 / 64 PO |
| PO avec CA, par année de commande : 2024 / 2025 / 2026 | 5 / 54 / 60 |
| PO sans CA, par année : 2025 / 2026 / sans date | 14 / 45 / 1 |
| Couples (PO, article) de `achat.qualite` dont une CA du PO cite l'article | 666 sur 956 (70 %) |

Les 60 PO sans CA sont surtout des commandes 2026 : analyses pas encore lancées, ou articles sans analyse (frais, accessoires). À confirmer avec le métier avant de les présenter comme des trous.

## 4. Règle de source par donnée

| Donnée | Source qui fait foi | Justification |
|---|---|---|
| Référence article, désignation | Sylob (article) ; IMPORT en repli | ERP |
| PO fournisseur | Sylob SE Achat | ERP |
| N° CA, date d'envoi en analyse, stade, prestations commandées, montant | Sylob SE Achat (CA chez `TARRERIAS ET CIE`) | La CA est une commande ERP |
| Article de l'échantillon dans la CA | Sylob `ligne_commentaire` (parsing), gsheet en contrôle | Champ libre, 73 % renseigné au format attendu |
| N° de BL de prestation, date de BL, montant livré | Sylob Cie Vente livraison | ERP |
| Statut MAT / SP / BAT (conforme, non reçu) | IMPORT colonnes AA à AD | Hors ERP, tenu par les Achats |
| FAIL d'inspection, n° de rapport | IMPORT colonne AF | Hors ERP |
| Décision conforme / non conforme datée, par stade | mails (`achat.qualite_decision`) | Email-first |
| Urgence, état du produit, état analyse, opérateur | gsheet ANALYSES EN ATTENTE | Document collaboratif tenu par le service qualité |
| À facturer, facturation faite, écart CA contre BL | gsheet FACTURATION INTERSITE, comparé à Sylob | Le gsheet existe parce que Sylob est parfois faux : on affiche les deux et l'écart |

## 5. Modèle cible proposé

### 5.1 Grain

**PO fournisseur x article x stade**, avec 0 à n CA par cellule. Un pivot par (PO, article) porte trois colonnes de statut MAT, SP, BAT (plus RECEP), chacune avec sa ou ses CA et sa date d'envoi en infobulle. Le grain actuel (PO, article) de `achat.qualite` reste la ligne de l'écran ; le stade devient des colonnes, pas des lignes.

### 5.2 Écran « Suivi des analyses »

| Colonne | Source | Détail |
|---|---|---|
| PO fournisseur | `achat.qualite.po_number` (normalisé 8 chiffres) | lien vers la fiche commande |
| Référence article | `achat.qualite.code_article` | |
| Désignation | `achat.qualite.designation` (IMPORT), Sylob en lot 2 | |
| Fournisseur | `achat.qualite.fournisseur` | |
| Statut MAT | IMPORT AA, normalisé | infobulle : n° CA, date d'envoi (Sylob), décision mail la plus récente |
| Statut SP | IMPORT AB | idem |
| Statut BAT | IMPORT AD | idem |
| Réception | IMPORT AG + badge réception Sylob existant | |
| Inspection | IMPORT AF (OK/FAIL + réf.) | lien Drive à réparer |
| CA | Sylob, liste des n° de CA du PO pour l'article | |
| N° BL prestation | Sylob Cie livraison | |
| NCR | IMPORT AH | |

Filtres : référence, désignation (texte), fournisseur, PO, n° CA, n° BL ; stade (MAT / SP / BAT / RECEP : n'affiche que les lignes ayant ce stade) ; un sélecteur de statut par colonne MAT, SP, BAT.

Normalisation des statuts affichés :

| Valeur IMPORT | Valeur écran |
|---|---|
| Non reçu, vide avec CA envoyée | en cours |
| Conforme, Validé, Conforme couteau | conforme |
| Non conforme | FAIL |
| Conforme au stade RECEP | réception |
| Aucune, « / », vide sans CA | non applicable |

La règle exacte (notamment « réception ») est une question métier, voir 7.

### 5.3 Écran « Facturation intersite »

Grain : une CA. Colonnes calquées sur FACTURATION INTERSITE : Stade, PO fournisseur, CA, S, D, M, C10, C10-50, C+50, R, Montant HT CA, Date de BL, BL, quantités côté BL, Montant HT BL, À facturer, Facturation faite. Sources : quantités et montants depuis Sylob (lignes `Pres%` de la CA, lignes de la livraison Cie), drapeaux À facturer / Facturation faite depuis le gsheet. Colonne calculée **Écart** : montant Sylob CA contre BL, et Sylob contre gsheet. Filtre : non facturé, écart non nul, stade, période.

### 5.4 Tables : proposer, ne rien créer

| Option | Contenu | Avis |
|---|---|---|
| Vue `achat.v_qualite_suivi` | `achat.qualite` + agrégats `qualite_decision` + CA Sylob | La donnée Sylob n'est pas dans `dtpf_sylob_prod` côté SE Achat CA et Cie Vente : il faut soit une copie MyReport, soit une table de staging |
| Table `achat.qualite_ca` (staging Sylob, full-refresh) | n° CA, PO, stade, date, montant, états, ref article parsée, BL Cie | Recommandé : un extrait nocturne de Sylob, pas une saisie. À valider : Sylob fait foi, donc idéalement une table MyReport plutôt qu'une copie dans `achat` |
| `achat.qualite_suivi` (existante, vide) | gsheet ANALYSES EN ATTENTE + ARCHIVES | À recâbler sur les 4 onglets actuels ; ne garder que les colonnes hors ERP (urgence, état produit, état analyse, opérateur) |
| `achat.qualite_facturation` (existante, vide) | gsheet FACTURATION INTERSITE | À recâbler, ne garder que À facturer / Facturation faite et les quantités côté gsheet pour l'écart |
| `achat.qualite` | inchangée | Le grain (PO, article) convient à la ligne d'écran |
| `v_qualite_fournisseur` | supprimer de l'écran ; garder la vue tant que `v_previsionnel` ou autre consommateur ne l'abandonne pas | Vérifier les dépendances avant `DROP` |

## 6. Découpage en livraisons

| Lot | Contenu | Nouvelle table | Effort |
|---|---|---|---|
| **Lot 1, rapide** | Supprimer le bloc Évaluation fournisseurs ; ajouter Désignation ; filtres PO, stade, statut MAT/SP/BAT ; normaliser les statuts (5.2) ; normaliser les PO (lpad 8) dans `/api/qualite` et `/api/qualite/rapports` ; agréger `qualite_decision` par (PO, stade) en infobulle avec la date de décision ; réparer ou retirer le lien Drive mort | Non | 1 à 2 jours |
| **Lot 2, CA Sylob** | Extrait Sylob des CA (SE Achat chez Cie, articles `Pres%`) avec parsing PO/stade/article et BL Cie ; colonnes CA, date d'envoi en infobulle, BL ; filtres CA et BL. Taux attendu : 66 % des PO, 70 % des couples (PO, article) | Staging `qualite_ca` ou table MyReport | 2 à 3 jours |
| **Lot 3, gsheet** | Transform des 4 onglets SUIVI DES ANALYSES vers `qualite_suivi` / `qualite_facturation` (recâblage, l'ancien profil est obsolète) ; urgence et état produit à l'écran ; écran Facturation intersite avec écart Sylob contre gsheet | Non (tables existantes, à revoir) | 2 à 3 jours |
| **Lot 4, optionnel** | Réconciliation automatique : CA présentes dans Sylob et absentes du gsheet, et inversement ; alerte facturation en attente | Non | 1 jour |

Prérequis lot 2 : scope du compte de service sur le DWH Sylob depuis l'API hébergée. L'API Azure ne joint pas le DWH on-premise (voir `Config.MYREPORT_SCHEMA`) : l'extrait doit passer par MyReport ou par l'ETL du poste.

## 7. Questions ouvertes au métier

1. **Statuts** : « en cours » est-il bien « Non reçu » dans l'IMPORT ? « réception » désigne-t-il la colonne RECEP (AG) ou une 4e valeur dans chaque colonne MAT/SP/BAT ? Que signifient les 51 cellules surlignées en rouge sur MAT/SP/BAT ?
2. **FAIL par stade** : où est noté un échec d'analyse MAT ou SP (aujourd'hui seulement « Non conforme » sur 2 lignes, et le FAIL d'inspection est global) ? Faut-il prendre les décisions mail de `qualite_decision` (30 non conformes MAT/SP/BAT) comme source ?
3. **Échantillon de conformité** (colonne AC, « Validé » à 660) : à afficher comme 4e stade ou à abandonner ?
4. **Date d'envoi en analyse** : date de création de la CA dans Sylob, ou date d'envoi du gsheet ? Elles divergent-elles ?
5. **Facturation intersite** : quels écarts Sylob contre gsheet rencontrez-vous concrètement (montant, quantité, CA non facturée) ? Qui coche « Facturation faite » ?
6. **Périmètre** : faut-il inclure les CA sans PO identifiable (« PLUSIEURS PO », 110 sans stade) et les CA RECEP ?
7. **PO sans CA** (60 sur 179) : normal (pas d'analyse requise) ou oubli à signaler ?
8. **Gsheet** : ANALYSES EN ATTENTE et ARCHIVES sont-ils bien la référence pour l'urgence et l'état du produit, et le restent-ils après le départ d'Andréa ?
9. **Évaluation fournisseurs** : suppression de l'écran seulement, ou abandon complet de l'indicateur (une vue Sylob `Qualite.vue_evaluation_fournisseur` existe) ?
