# Cadrage — Fiche Achat (Purchase Sheet) dans FUSEAU

> Chantier 6. Objectif : consultation des fiches existantes + création de nouvelles.
> Basé sur le template réel `FOR-ACH-03-12 Purchase sheet` et le dossier exemple
> `Service_Achat/00182725-Heritage black et inox-NOSKI`. Créé le 2026-07-20.

---

## 1. Ce qu'est une Fiche Achat (PS)

Fiche récapitulative et détaillée d'un produit, base d'échange **avec le fournisseur** ET **en interne**. Aujourd'hui : un **xlsx** (template `FOR-ACH-03-12`, 2 variantes : « Produits uniques » et « Ménagère et sets ») rempli puis exporté en **PDF** (`PS-<PO>-<désignation>-<code_article>-<fournisseur>.pdf`), rangé par commande.

**Dossier type par PO** (`Service_Achat/<PO>-<désignation>-<fournisseur>/`) :
- `PS-…pdf` — la Fiche Achat
- `PI-…pdf` — proforma
- `PO-…pdf` — commande
- sous-dossiers `Modifiable/` (xlsx source) et `Signé/`

## 2. Blocs du template (→ où Andréa pêche l'info en interne)

> La colonne de droite = **à qui/où Andréa va chercher l'info** (elle consolide seule). C'est la cartographie à capturer avant son départ.

| Bloc template | Contenu | Source interne (Andréa demande à) |
|---|---|---|
| DESCRIPTION PRODUCT / SUPPLIER | Fournisseur, références + noms produits | Achats / Sourcing (Julia) |
| TRANSPORT | Forwarder, type, port destination (Fos), ETD | Achats / Logistique |
| PACKAGING INFORMATIONS | Nb pièces/sets, dimensions Item / Inner / Master | Logistique (Emmanuelle) |
| PARTICULAR DOC REQUIRED | Docs légaux exigés | Achats |
| SAMPLE | Échantillons de test, port payé par, envois | Sourcing / Qualité |
| PRODUCT MATERIAL — METAL PART | Épaisseur, longueur, qualité, **% chrome**, traitement thermique, finition | Sourcing / Qualité |
| PRODUCT MATERIAL — HANDLE | Matière manche, **Pantone** | Design |
| STAMPING | Marquage lame/produit, dimensions, images | Design |
| PRODUCTION / PACKING | Plan de prod, image emballage, dimensions master carton | Logistique / Design |
| PICTURE OF PRODUCT | Visuel produit | Design |
| MORE INFORMATION — EAN | Item = EAN13, Inner = EAN14 SPCB, Master = EAN14 PCB, N° lot en code-barres | Logistique (Emmanuelle) |
| FRENCH TRANSLATION | N° item + désignation FR | Produit (Jonatan) |

➜ La Fiche Achat est le **document pivot du Circuit A** (nouveau produit), **consolidé par Andréa seule** auprès de ces services. Elle recoupe des données déjà dans FUSEAU : nomenclature (`article_nomenclature`), packaging/dimensions (Sylob V25), EAN, fournisseur — d'où le fort potentiel de pré-remplissage.

## 3. Approche proposée (2 phases)

### Phase A — Consultation (rapide, fort ROI, à capter avant le départ d'Andréa)
- **Indexer** les fiches existantes : crawler `Service_Achat/<PO>/` (+ Drive « Purchasing department ») pour les fichiers `PS-*.pdf`, extraire PO / code_article / désignation / fournisseur du nom (conventions du sondage PJ).
- Table **`achat.fiche_achat_doc`** (index) : `po_number, code_article, designation, fournisseur, chemin/URL, date_maj`. Même pattern que `qualite_doc`.
- **Onglet / vue FUSEAU** : rechercher une fiche par code article ou PO, lien pour ouvrir le PDF. Colonne « Fiche achat » dans Suivi commande (clic → ouvre le PS).

### Phase B — Création (chantier lourd)

⚠️ **Correction de modèle (20/07)** : la fiche est remplie par **Andréa SEULE**, qui va « à la pêche aux infos » en interne auprès des services. Ce n'est **pas** un formulaire collaboratif multi-services. Conséquences :

- **Un seul formulaire, un seul utilisateur** (Andréa, puis Marlène/successeur). Pas de workflow d'assignation par service.
- **La valeur = réduire la pêche** : pré-remplir un maximum (les ~60% déjà dans FUSEAU/Sylob, cf. §4b) et, pour les champs restants, **indiquer où/à qui aller chercher l'info** (colonne « source interne » ci-dessous). Cela **capture le savoir tacite d'Andréa** (qui sait à qui demander quoi) avant son départ le 31/07 — c'est le vrai enjeu de pérennité.
- Génération : remplir le **template xlsx** (`FOR-ACH-03-12`) puis export PDF, ou stocker en base (`achat.fiche_achat` + lignes) et générer le PDF (gabarit = PS-00182725).
- Clé pivot = **code_article** (créé par Emmanuelle dès la commande fournisseur), code provisoire `JJMMAAHHMM` avant attribution.

## 4. Source de vérité (tranché 20/07) + à capter avec Andréa avant le 31/07

**Source de vérité = le SERVEUR** (confirmé Antho). Chemin :
`\\Srv-files-pom\partage\ADA\METIER\SUIVI CDES IMPORT\<année>\COMMANDES ET FICHES ACHATS\<PO>-<désignation>-<fournisseur>\PS-*.pdf`
→ déjà couvert par le **grant AD du ticket** (lecture récursive sur `SUIVI CDES IMPORT\`). Le crawler Phase A tournera donc sur l'hôte LAN sous le compte de service (comme les autres ETL) ; non atteignable depuis le sandbox.

Workflow **tranché (20/07)** : Andréa remplit **seule**, en pêchant l'info en interne. Reste à capter avant le 31/07 :
- La **carte de sourcing interne** : pour chaque champ non pré-rempli, à qui elle demande (compléter la colonne « source interne » du §2) — c'est son savoir tacite à sauvegarder.
- Les 2 variantes (Produits uniques vs Ménagère/sets) : mêmes blocs ? différences ?
- Ce qui doit être **modifiable dans le temps** (les lignes bougent pendant la négo : qté, prix).

## 4b. Structure finale de référence — PS-00182725 (validée « parfaite » par Antho)

Exemple : SET OF 4 KNIVES LAG HERITAGE BLACK PVD (réf 20110064, NOSKI). Champ → valeur → source de pré-remplissage possible :

| Champ | Valeur exemple | Pré-remplissable depuis |
|---|---|---|
| Supplier | NOSKI | commande.fournisseur |
| Référence / Name | 20110064 / SET OF 4 KNIVES LAG HERITAGE… | code_article / désignation |
| Port destination / ETD | FOS SUR MER / 2026-08-30 | ot_transport (ETD), constante Fos |
| Packaging Item/Inner/Master | 4 / 6 / 6 | Sylob V25 (PCB/SPCB) / article_nomenclature |
| Shipping marks | GW/NW - Item - EAN - Designation | règle standard |
| Metal : thickness/length/quality/**chrome%**/heat/finishing | 12mm / 240mm / 2CR14 / 13 / Yes / Mirror + Black PVD | nomenclature + **qualité (chrome)** |
| Handle : material / pantone | Stainless steel + stamping of bee / Steel | à saisir (Design/Sourcing) |
| Stamping / dims | LAGUIOLE HERITAGE / 4,5 x 15,5 | à saisir (Design) |
| Master carton dims (L/W/H) | (bas de fiche) | Sylob dimensions |
| EAN Item/Inner/Master (13 / 14 SPCB / 14 PCB) | (bas de fiche) | Sylob / référentiel EAN |
| French translation | item + désignation FR | Jonatan / désignation FR |

➜ **~60% des champs sont déjà dans FUSEAU/Sylob** → le formulaire de création (Phase B) peut être largement pré-rempli ; l'utilisateur ne saisit que le spécifique (handle, stamping, docs). Le `PS-00182725` (xlsx `Modifiable/` + PDF signé `Signé/`) est le gabarit de sortie cible.

## 5. Reco de démarrage
Commencer par la **Phase A (consultation)** : indexer les `PS-*.pdf` existants et les rendre consultables/liables depuis FUSEAU. C'est immédiatement utile, réutilise le pattern `qualite_doc`, et ne dépend pas du workflow de création (qui, lui, demande le cadrage détaillé avec Andréa).
