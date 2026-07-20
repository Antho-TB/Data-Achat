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

## 2. Blocs du template (→ services contributeurs, Circuit A)

| Bloc template | Contenu | Service |
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

➜ La Fiche Achat est donc le **document pivot du Circuit A** (nouveau produit), alimenté par 5 services. Elle recoupe des données déjà dans FUSEAU : nomenclature (`article_nomenclature`), packaging/dimensions (Sylob V25), EAN, fournisseur.

## 3. Approche proposée (2 phases)

### Phase A — Consultation (rapide, fort ROI, à capter avant le départ d'Andréa)
- **Indexer** les fiches existantes : crawler `Service_Achat/<PO>/` (+ Drive « Purchasing department ») pour les fichiers `PS-*.pdf`, extraire PO / code_article / désignation / fournisseur du nom (conventions du sondage PJ).
- Table **`achat.fiche_achat_doc`** (index) : `po_number, code_article, designation, fournisseur, chemin/URL, date_maj`. Même pattern que `qualite_doc`.
- **Onglet / vue FUSEAU** : rechercher une fiche par code article ou PO, lien pour ouvrir le PDF. Colonne « Fiche achat » dans Suivi commande (clic → ouvre le PS).

### Phase B — Création (chantier lourd, après cadrage avec Andréa)
- **Formulaire par bloc** (les 12 blocs ci-dessus), pré-rempli depuis les données FUSEAU déjà connues (nomenclature, dimensions Sylob, EAN, fournisseur) → l'utilisateur complète le reste.
- Génération : soit remplir le **template xlsx** (`FOR-ACH-03-12`) puis export PDF, soit stocker en base (`achat.fiche_achat` + lignes) et générer le PDF à la demande.
- Workflow collaboratif 5 services (cf. Circuit A) : à terme, chaque service remplit son bloc.
- Clé pivot = **code_article** (créé par Emmanuelle dès la commande fournisseur), avec le code provisoire `JJMMAAHHMM` avant attribution.

## 4. À capter avec Andréa avant le 31/07
- Où sont **toutes** les fiches existantes (serveur `Service_Achat` ? Drive « Purchasing department » ? les deux ?) → source de vérité à figer.
- Le **workflow réel** de remplissage (qui remplit quel bloc, dans quel ordre, à quel moment du Circuit A).
- Les 2 variantes (Produits uniques vs Ménagère/sets) : mêmes blocs ? différences ?
- Ce qui doit être **modifiable dans le temps** (les lignes bougent pendant la négo : qté, prix).

## 5. Reco de démarrage
Commencer par la **Phase A (consultation)** : indexer les `PS-*.pdf` existants et les rendre consultables/liables depuis FUSEAU. C'est immédiatement utile, réutilise le pattern `qualite_doc`, et ne dépend pas du workflow de création (qui, lui, demande le cadrage détaillé avec Andréa).
