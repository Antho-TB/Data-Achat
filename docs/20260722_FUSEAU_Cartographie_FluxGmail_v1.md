# Cartographie exhaustive de l'information circulant par Gmail — FUSEAU / Data-Achat

> Rédigé le 2026-07-22. Objectif : recenser **toute** l'information critique qui transite par le
> flux Gmail informel (email-first TB Groupe), au-delà des seuls PO/prix/dates — retards imprévus,
> décisions Commerce (Eric T, David), Supply Chain (Emmanuelle), Design (Clarisse), qualité, etc.
> Base de cadrage pour la tâche planifiée Cowork de captation des threads.

> **Principe "email-first"** (confirmé `achatanalyser-mail/SKILL.md`) : les échanges fournisseurs
> passent d'abord par Gmail (Andréa + Marlène), jamais par Sylob directement. Aujourd'hui, seul le
> pipeline **PJ Gmail → `ot_transport`** est outillé ; la quasi-totalité du reste circule sans captation.

Légende statut : **Capté** = ingéré dans une table `achat.*` · **Partiel** = table cible existe mais
alimentation incomplète/manuelle/pilote · **Non capté** = circule uniquement par mail.

## 1. Par catégorie

### 1.1 Commande / PO / prix (Circuit B réappro + Circuit A)
| Type d'info | Émetteur | Étape | Destinataire | Table cible | Statut | Réf |
|---|---|---|---|---|---|---|
| Confirmation PO (PO#, MEN#, N° lot) | Fournisseur / TB China | B & A envoi | Andréa (Marlène copie) | `commande` | Partiel (source Excel) | achatanalyser-mail |
| Prix unitaire négocié (MOQ, incoterms) | Fournisseur ; validé Commerce | négociation | Andréa | `commande.prix_unitaire` / Sylob | Partiel (Sylob = vérité) | questionnaire Q5-6 |
| Quantité / écarts qté | Fournisseur | B & A | Andréa | `commande.quantite` | Non capté | achatanalyser-mail |
| ETD confirmé | Fournisseur / TB China | production | Andréa | `commande.etd_confirme` | Partiel (sémantique à trancher) | plan_action pt 1 |
| Incohérences prix/qté/date mail↔base | (détection) | transverse | Andréa | alerte | Non capté | achatanalyser-mail |

### 1.2 Logistique maritime / transport (seul flux outillé)
| Type d'info | Émetteur | Étape | Destinataire | Table cible | Statut | Réf |
|---|---|---|---|---|---|---|
| N° BL, N° conteneur | Transitaire QUALITAIR ; fournisseur | expédition | Andréa | `ot_transport` | **Capté** (Plan A prouvé) | plan_action 30/06 |
| ETD réel / ETA | Transitaire | logistique | Andréa | `ot_transport.etd_reel/.eta` | Partiel→Capté | sources #4 |
| **Changements successifs ETA / date livraison** | Transitaire (corps + PJ) | logistique | Andréa/Marlène | `ot_transport_date_evenement` (à créer) | **Non capté** (spec 22/07) | Spec ETA |
| **Retard imprévu majeur (grève, incident)** | Transitaire / TB China | logistique | Andréa | aucune (à qualifier) | **Non capté** (aucune source) | plan_action pt 5 |
| Raison du retard (texte libre) | Transitaire / fournisseur / TB China | logistique | Andréa | `commande_annotation` / parsing | **Non capté** (décidé : parser le corps) | RetoursDemo14h §🟡-2 |
| Transporteur / nom navire / POL / POD | Transitaire | logistique | Andréa | `commande.transitaire/.nom_navire`, `ot_transport` | Partiel | sources #4 |
| Annonce livraison conteneur / dédouanement | Transitaire (douanes via lui) | logistique | Andréa | `ot_transport.date_livraison` | Partiel | Circuit A2 |
| Planning de livraison (1 sem. avant) | **Andréa (émettrice)** | logistique interne | Logistique + RH + Qualité | à créer | Non capté (mail sortant) | Précisions Emmanuelle 30/06 |

### 1.3 Qualité (DEKRA, labo GDD/SPECTRO, décision conforme/non conforme)
| Type d'info | Émetteur | Étape | Destinataire | Table cible | Statut | Réf |
|---|---|---|---|---|---|---|
| Rapport inspection DEKRA (N° `CA…`, OK/FAIL/BAT) | DEKRA | inspection | Andréa | `qualite`, `qualite_doc` | Partiel (pilote Drive) | sources #1 |
| Rapport analyse labo (chrome %, dureté HRC) | Labo GDD / SPECTRO | analyse MAT/SP/BAT | Andréa | `qualite_analyse` | Partiel (pilote OCR) | sources #2 |
| **Décision conforme / NON conforme** | **Eric T (Commerce)** | validation | Andréa | `qualite`/`commande` — à parser | **Non capté** (mail, asymétrique) | questionnaire Q1-2 |
| Commande d'analyse (déclenchement labo) | Andréa | qualité | Labo | `qualite_suivi` | Partiel (transform manquant) | sources #5 |
| Suivi/facturation analyses (CA, BL labo) | Labo / Andréa | qualité | Andréa | `qualite_facturation` | Partiel | modele_semantique |
| Décision post-FAIL / NCR | Qualité + Commerce | qualité | Andréa | `qualite.ncr` | Non capté (dépend boîte mail) | plan_action 25/06 |

### 1.4 Design / Artwork (Clarisse)
| Type d'info | Émetteur | Étape | Destinataire | Table cible | Statut | Réf |
|---|---|---|---|---|---|---|
| Statut validation artwork | **Clarisse** | packaging | Andréa | `artwork_statut` (gsheet) | Partiel | sources #3 |
| Artwork envoyé TB China (+ PO/PS signé) | Design / Andréa | envoi cmd | TB China | `artwork` | Non capté | Circuit A2 |
| **Validation boîte imprimée / produit / dimensions** | Design | checkpoints | Andréa | aucune | **Non capté** | Gaps board |
| Étiquettes, shipping marks, marquage | Design | Circuit A | Andréa / TB China | `article_nomenclature` (Matrice) | Partiel | cadrage_fiche_achat §2 |
| Pantone / matière manche | Design | Circuit A | Andréa | `article_nomenclature.pantone_manche` | Partiel | cadrage_fiche_achat §4b |

### 1.5 Paiement / Compta
| Type d'info | Émetteur | Étape | Destinataire | Table cible | Statut | Réf |
|---|---|---|---|---|---|---|
| N° facture fournisseur | Fournisseur | paiement | Andréa/Compta | `commande.n_facture`, `ot_transport.n_facture` | Partiel | achat_schema |
| **Packing list** (3e pièce liasse) | Fournisseur | paiement | Andréa/Compta | aucune colonne | **Non capté** (source non identifiée) | questionnaire Q13 |
| Acompte / solde versé | **Marlène (saisie)** / Compta | paiement | — | `acompte.montant_acompte` | Partiel (absent de Sylob) | plan_action Lot 3 |
| Réclamation fournisseur (oubli acompte) | Fournisseur | paiement | Andréa | `acompte` (à afficher UI) | Non capté | audit RetoursMetier |
| Déclenchement paiement = BL+facture+packing | Compta / Andréa | paiement (Ph.4) | Compta | modèle à créer | Non capté | questionnaire Q13 |
| **Flag promo / urgence** | Commerce (Eric/David) | cmd OU milieu circuit | Andréa | aucun flag | **Non capté** | questionnaire Q14 |

### 1.6 Circuit A amont (code article / prototype / proforma / PS / fiche achat)
| Type d'info | Émetteur | Étape | Destinataire | Table cible | Statut | Réf |
|---|---|---|---|---|---|---|
| **Demande de code article (informel)** | **Eric T / Design** | très amont | Emmanuelle / Andréa | aucune (N-N non résolue) | **Non capté** (boîte Eric T) | questionnaire Q10 |
| Prototype (pré-gamme) | GDD (BaseCamp) / TB (Gmail) | proto | Olivier | aucune (pas d'ID proto) | **Non capté** | Précisions Emmanuelle |
| Code article créé (pivot amont) | **Emmanuelle** | dès la commande frs | Clarisse + Andréa | `produit.code_article` | Partiel | Précisions Emmanuelle |
| Proforma (PI) — contrôler + signer | Fournisseur | validation | Andréa | `commande.doc_proforma` | Non capté (alim manuelle) | Gaps board |
| PS signé (Purchase Sheet) | Andréa ↔ fournisseur | envoi cmd | TB China | `commande.ps_signe` / `fiche_achat_doc` (à créer) | Non capté | cadrage_fiche_achat §3 |
| Infos sourcing China | **Julia (Sourcing)** | fiche achat | Andréa | bloc fiche achat | Non capté | cadrage_fiche_achat §2 |
| MAT / SP / échantillon conformité | Labo + Andréa | Circuit A1 | Andréa | `commande`, `qualite` | Partiel (Excel) | plan_action §5 |

## 2. Acteurs — ce que chacun fait transiter par mail

- **Andréa** (Assistante Achats, part 31/07) : nœud central, reçoit tout, consolide la fiche achat, passe les commandes Sylob, émet le planning de livraison, saisit l'IMPORT. Sa boîte = cible d'ingestion ; son savoir tacite = enjeu de pérennité.
- **Marlène** (Responsable Achats, reste) : en copie systématique mais ne reçoit pas tout ce qu'Andréa reçoit ; saisit acompte/solde.
- **Maxence** : boîte Andréa transférée à lui, Marlène en copie (résolution Q19).
- **Eric Tarrerias** (Commerce) : décideur non-conformité par mail ; bloc commercial fiche ; déclenche demande code article ; pose flag promo. Boîte à parser.
- **David + Charles** (Commerce) : blocs commerciaux, dossier PO/PS, validation commande, ventes → flag promo.
- **Emmanuelle** (Supply Chain & Data Analyst) : crée le code article Sylob dès la commande (prérequis gamme), bloc PCB/SPCB/EAN.
- **Clarisse** (Design) : statut artwork, validation boîte, marquage, étiquettes, Pantone.
- **Julia** (Sourcing) : infos China (fournisseur, production, conformité).
- **Olivier** (Appro) : suggestion réappro ; workflow prototype GDD/BaseCamp / « code affaire ».
- **Jonatan** (Produit) : nom article FR/EN, gamme.
- **TB China** : relais fournisseurs Chine, reçoit PO+PS+Artwork, renvoie confirmations/BAT.
- **QUALITAIR / SEALOGIS** (transitaire) : ETD/ETA/retard imprévu, BL, conteneur, navire, livraison, douanes.
- **DEKRA** : demandes/rapports d'inspection (OK/FAIL/BAT).
- **Labo GDD / SPECTRO** : rapports d'analyses (chrome, dureté), commande d'analyse, facturation.
- **Logistique** (interne) : reçoit le planning de livraison d'Andréa.
- **Compta** : paiement sur liasse BL+facture+packing list (Phase 4).

## 3. Les "trous" — info critique en mail, non captée aujourd'hui

**Priorité haute :**
1. **Décision de non-conformité d'Eric T** — seul signal de rejet qualité, par mail, asymétrique.
2. **Raison / motif du retard** (dont imprévus grève/incident) — à parser du corps ; imprévu majeur = aucune source.
3. **Changements successifs d'ETA / date livraison** — COALESCE garde la 1re valeur ; spec 22/07 non codée.
4. **Packing list** — 3e pièce du paiement, aucune colonne dans le schéma.
5. **Demande de code article / lien prototype↔code** — échanges informels boîte Eric T, N-N non résolue.

**Priorité moyenne :**
6. Validation boîte imprimée / dimensions par Design (checkpoints non modélisés).
7. Flag promo / urgence (Commerce) — aucun champ.
8. Proforma (PI) et PS signé — colonnes existent, non alimentées depuis les mails.
9. Acompte réclamé/oublié — donnée existe, non remontée dans l'UI.
10. Écarts prix/quantité mail↔base — détection décrite, jamais branchée.

**Priorité basse / process :**
11. Infos sourcing China (Julia), suivi analyses (transform non écrit), planning de livraison sortant d'Andréa.

## 4. Décisions métier déjà actées sur l'extraction des mails

| Décision | Contenu | Réf |
|---|---|---|
| Parser le corps d'Eric T pour la non-conformité | Conforme = implicite ; non conforme = mail explicite. Parser la boîte Commerce. | questionnaire Q1 (07/07) |
| Extraire la raison du retard du corps | Pas de saisie structurée ; cible `commande_annotation`. | RetoursDemo14h §🟡-2 |
| Cibler la boîte d'Andréa pour l'ingestion | Marlène en copie mais trous ; boîte transférée à Maxence + Marlène copie. | plan_action §25/06 ; Q19 |
| Write-path Gmail = pattern A découplé | BL Gmail → UPSERT `ot_transport` (jamais INSERT direct dans `commande` full-refresh). Annotations → `commande_annotation`. | plan_action 30/06 ; achat-gmail-dwh |
| Vérité = dernière date transmise (abandon COALESCE) | ETA/livraison : valeur la plus récente gagne ; table événements + alerte couleur. | Spec ETA §2 |
| Explorer le « code affaire » GDD comme modèle d'ID prototype | Demande code article = Gmail informel, N-N ; piste BDD GDD. | questionnaire Q10 |
| Ne PAS inventer de colonne packing list | Identifier la source d'abord (parsing mail ? saisie ?). | questionnaire Q13 |
| Extraire échantillons DEKRA/labo (Drive+mail) | Index `qualite_doc` (FAIL→PDF) + mesures `qualite_analyse`. Priorité = décision conforme/non conforme > chrome brut. | plan_action #7 + 02/07 |
| Convention nommage PDF qualité avec code article | Évolution process côté Qualité. | RetoursDemo14h §🟡-4 |
| Règle retard paiement = ETD_BL + 15 j | Implémentée ; date de réf vient du BL (mail/PJ). | questionnaire Q15 |
| Flag promo modifiable à plusieurs étapes | Posé à la commande OU en milieu de circuit. Non modélisé. | questionnaire Q14 |
