# Audit champ-par-champ achat.* vs Sylob V25 (2026-07-02)

> Directive Antho : vérifier que les données captées par le circuit ETL Excel/Gsheet + Gmail
> et injectées dans `dtpf_sylob_prod.achat.*` n'existent pas déjà dans Sylob (V25). FUSEAU est
> **provisoire** — la cible est de réintégrer ces données dans le circuit Sylob natif (API
> écriture, nouveaux champs personnalisés `sup_*`), pas de dupliquer un référentiel parallèle.

Périmètre audité : `tarrerias_production_dwh` V25 (192.168.102.41:5432), société
`TARRERIAS_SE_TARRERIAS_BONJEAN`, schémas `Achat`, `Article`, `Fournisseur`, `Qualite`,
`Concevoir`, `Finances`. Vérification à la fois structurelle (colonne existe) ET
**opérationnelle** (colonne réellement peuplée — une colonne vide ne compte pas comme "oui").

## Correction importante vs l'audit précédent (même jour, table-level)

L'audit initial (niveau table) disait **acompte : non** dans Sylob. C'est **faux au niveau
schéma** — corrigé ci-dessous : les colonnes existent mais ne sont quasiment pas utilisées.

## Résultat détaillé par table `achat.*`

### `commande` / `acompte` → `Achat.f_commandeachat` + `f_lignecommandeachat` + `f_receptionachat`
**Structure : oui, quasi 1:1.** `f_commandeachat` porte déjà `montant_de_l_acompte`,
`pourcentage_d_acompte`, `net_a_payer`, `total_ht/ttc/tva`, dates, statuts.
**MAIS opérationnel : quasi jamais alimenté.**
- `montant_de_l_acompte` / `pourcentage_d_acompte` : colonnes remplies à 100% (106380/106380
  lignes) mais **valeur non-nulle réelle seulement 228 et 28 lignes** (0.2%/0.03%) → Sylob a
  la capacité mais TB ne saisit quasiment jamais l'acompte dedans. Notre `achat.acompte`
  capture une donnée qui existe *nativement dans Sylob* mais qui n'y est pas *pratiquée*.
  → **Cible correcte : pousser nos données d'acompte dans ces champs Sylob natifs (API
  écriture), pas créer de nouveaux champs.**
- Transport/ETD : `f_commandeachat` a déjà `sup_date_dembarquement`, `sup_etd_confirme`,
  `sup_etd_demande`, `sup_statut_pub_recaptransport` (custom `sup_*`, donc déjà "câblés" côté
  Sylob). Population réelle : **11 / 63 / 839 lignes sur 106380** (quasi nul, et dates
  trouvées datent de 2021-2022 — pas la campagne 2026 en cours). `sup_statut_pub_recaptransport`
  est actif lui (62823 Oui / 43556 Non) mais c'est un statut de publication, pas une date.
  → **`ot_transport` (nos 43 conteneurs chargés ce jour) n'a PAS d'équivalent actif dans
  Sylob aujourd'hui**, mais les champs `sup_etd_*`/`sup_date_dembarquement` existent déjà et
  sont clairement prévus pour ça — juste jamais alimentés. Piste sérieuse pour la
  réintégration : écrire nos ETD/ETA confirmés dans ces champs plutôt qu'en créer de
  nouveaux.
- `f_lignecommandeachat` a aussi `sup_nb_palette_europe`, `sup_nb_total_de_colis`,
  `sup_nombre_dunite_logistique`, `sup_poids_suggestion_ot`, `sup_volume` — **ces champs sont
  actifs** (~99.97% remplis sur 126308 lignes). Logistique/volumétrie déjà vivante côté Sylob.

### `produit` → `Article.af_article`
**Oui, largement.** Cf. audit initial : EAN13 natif (90%), EAN14/PCB/dimensions/poids
custom `sup_*` peuplés à 84-97% sur 9827 articles. Gamme/famille commerciale native
(`a_famillearticle`/`a_grandefamillearticle`/`a_sousfamillearticle`).
`sylob_code_article`/`sylob_last_price`/`sylob_synced_at` (nos colonnes de matching) n'ont
par construction pas d'équivalent — c'est notre couche de liaison FUSEAU↔Sylob.

### `article_nomenclature` (packaging+gamme+HS) → `Article.af_article` + `Concevoir`
Confirmé : packaging/EAN/dimensions déjà natifs (cf. `produit`). **HS code généraliste
absent** (`sup_code_douanier_us` seulement 7% rempli, probablement US only, pas de code
douanier global). `matiere_lame`/`chrome_pct`/`finition`/`matiere_manche` (nos colonnes
techniques matière) **absents de Sylob** — pas de concept caractéristique matière/traitement
dans `af_article` natif ni dans `a_caracteristiquearticle` audité (générique, pas de valeur
métier trouvée pour ces champs précis). **Nomenclature composant** (BOM) : `af_article` a
bien `nomenclature_de_produit`/`niveau_de_nomenclature`, mais le détail composant+packaging
lié n'a pas été audité au niveau ligne de nomenclature (à creuser si besoin, module
`Concevoir`/BOM non exploré en détail).

### `ot_transport` → partiellement `Achat.f_commandeachat.sup_etd_*` (cf. ci-dessus)
**Corrigé par rapport à l'audit initial ("non" trop tranché).** Les champs existent côté
Sylob mais ne sont pas utilisés. Conclusion opérationnelle : **notre donnée reste la seule
source vivante aujourd'hui**, mais la cible de réintégration a un point d'ancrage déjà prévu
dans le schéma Sylob (`sup_date_dembarquement`, `sup_etd_confirme`) — pas besoin de demander
de nouveaux champs custom à Nubo, juste de les faire vivre.

### `artwork` / `artwork_statut` → **non, confirmé.** Aucun concept design/artwork/BAT visuel
dans les schémas Achat/Article/Qualite/Concevoir audités.

### `qualite` → `Qualite.f_controlequalitereception` (partiel, grain différent) +
`Achat.f_lignecommandeachat.sup_rapport_dinspection`/`sup_certificat_matiere`
`f_controlequalitereception` est un contrôle réception générique (Oui/Non/commentaire/date),
**pas de stades MAT/SP/BAT** ni de détail conformité comme notre `achat.qualite`. Les flags
`sup_rapport_dinspection`/`sup_certificat_matiere` existent **au niveau ligne de commande**
(pas seulement article, comme trouvé dans le premier audit) et sont actifs (~99.99% remplis
sur 126308 lignes) — mais restent des booléens Oui/Non, pas des liens fichier. **Notre valeur
ajoutée (stades, conformité détaillée, NCR) reste réelle.**

### `qualite_doc` / `qualite_analyse` → **non, confirmé.** `Qualite.f_fichenonconformite` est
riche (causes, défauts, coûts, décisions, dérogation — cf. `sup_cout_dollar`,
`sup_detectee_a_la_reception`, `sup_n_de_lot`) mais **ne contient aucune mesure labo**
(chrome %, dureté HRC) ni lien vers un fichier PDF de rapport. Notre `qualite_analyse`
(mesures SPECTRO) et `qualite_doc` (index fichiers Drive/serveur) n'ont pas d'équivalent.
**Cible réintégration plausible** : les champs `sup_*` de `f_fichenonconformite` montrent que
Nubo/Sylob a l'habitude d'ajouter des `sup_*` sur ce module — une extension côté NC pourrait
accueillir nos mesures si le besoin est validé métier.

### `qualite_suivi` / `qualite_facturation` → **non, confirmé.** Pas de concept
"facturation labo" (nb_spectro/nb_durete/montant_ht_ca) dans Achat/Qualite/Finances audités.

### `fournisseur_ca` → `Achat.vue_commande_achat` (agrégation) + `Fournisseur.af_fournisseur`
**Oui, dérivable.** CA cumulé calculable depuis `vue_commande_achat`, pas de table CA
pré-agrégée mais la donnée source existe.

### `commande_annotation` → **non, et normal.** C'est explicitement notre couche
d'annotation métier FUSEAU (survit au full-refresh) — pas vocation à exister ailleurs tant
que FUSEAU reste l'outil de saisie ; si réintégré, deviendrait un champ Sylob natif
(commentaire sur ligne de commande existe déjà : `f_lignecommandeachat.commentaire`).

## Synthèse actionnable pour la réintégration Sylob

| Donnée FUSEAU | Statut Sylob | Action réintégration recommandée |
|---|---|---|
| Acompte (montant/%) | Champ natif existe, non pratiqué | **Écrire dans les champs natifs existants** (`montant_de_l_acompte`, `pourcentage_d_acompte`) — pas de nouveau champ à demander |
| ETD/ETA/embarquement (ot_transport) | Champs `sup_*` existent, non pratiqués | **Écrire dans `sup_date_dembarquement`/`sup_etd_confirme`** — idem, champ déjà prévu |
| Dimensions/EAN packaging | Natif, déjà peuplé 84-97% | **Ne rien réintégrer** — lire directement `af_article.sup_*`, arrêter la double-saisie Excel côté Andréa si possible |
| Design/artwork | Absent | Nouveau champ custom à demander à Nubo si réintégration voulue |
| Qualité mesures labo (chrome/dureté) | Absent | Nouveau champ custom sur `f_fichenonconformite` ou nouvelle table Sylob à évaluer avec Emmanuelle |
| Qualité doc (lien fichier) | Absent (flag Oui/Non seulement) | Nouveau champ custom (URL) à demander à Nubo |
| Qualité suivi/facturation labo | Absent | Nouveau module/champs à demander (périmètre financier, voir avec Finances) |
| HS code généraliste | Quasi absent (US only, 7%) | À vérifier avec GDD/douane si un champ existe ailleurs (Concevoir non exploré en détail) |

## Scripts utilisés
`sql/20260702_audit_achat_columns.sql`, `sql/20260702_audit_sylob_columns.sql`,
`sql/20260702_audit_sylob_columns2.sql`, `sql/20260702_audit_sylob_populations.sql`,
`sql/20260702_audit_sylob_samples2.sql`.
