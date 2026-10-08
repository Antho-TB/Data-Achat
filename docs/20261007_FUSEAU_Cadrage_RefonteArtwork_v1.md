# Cadrage : refonte de l'onglet Artwork (retours de la démo du 06/10)

> Statut : **à valider avant code.** Deux décisions sont à prendre avec Clarisse
> (§2). Livré le 07/10 sans attendre : retrait des deux graphiques de l'onglet.

## 1. Ce que le métier demande (démo du 06/10, notes d'Antho)

1. Un identifiant propre à chaque artwork. Un article peut avoir plusieurs artworks, un artwork n'a qu'un article.
2. Trois dates distinctes : création, validation, mise à jour.
3. Voir l'artwork (lien vers le PDF du Drive).
4. Ajouter et modifier des lignes depuis FUSEAU.
5. Garder les deux tableaux du gsheet : artworks en attente, et archive pour rechercher l'existant.
6. Quand Clarisse valide, Maxence archive à la main une fois traité : automatiser cette suite.
7. Clarisse devient utilisatrice de FUSEAU.
8. Plus tard : contrôler l'artwork fournisseur contre celui de Clarisse (textes, EAN, SPCB, PCB, référence, désignation).

## 2. Décisions à prendre

### 2.1 Qui fait foi : FUSEAU ou le gsheet ?

Aujourd'hui, `achat.artwork_statut` est un miroir du gsheet `LIS-CON-28-0`,
rechargé chaque jour à 07h. Un `PUT /api/artwork/{code_article}` existe déjà,
mais ce qu'il écrit est écrasé au chargement suivant : c'est la contradiction
notée au §5.2 du plan d'action.

| Option | Principe | Conséquence |
|---|---|---|
| **A (recommandée)** | FUSEAU devient la source. Reprise unique du gsheet, puis Clarisse saisit dans FUSEAU. Le gsheet est figé en lecture seule, gardé comme archive | Une seule vérité, historique et ID maîtrisés. Clarisse change d'outil : à accompagner |
| B | Le gsheet reste la source, FUSEAU l'affiche | Pas de saisie dans FUSEAU, ce qui contredit les points 4 et 6 |
| C (à éviter) | Saisie des deux côtés, synchronisation | Conflits à arbitrer en permanence, deux sources qui divergent |

Les points 4, 6 et 7 de la démo vont tous vers A.

### 2.2 Forme de l'identifiant

**Tranché le 08/10 avec Clarisse : n° d'article et date concaténés**, par exemple
`32030006-20261008`. Deux garde-fous pour éviter les pièges de ce format :

- la date est celle de la **création** de l'artwork, figée à la création : l'ID ne
  change jamais, même si une date est corrigée ensuite ;
- deux artworks du même article créés le même jour reçoivent un suffixe :
  `32030006-20261008`, puis `32030006-20261008-2`.

L'ID est calculé par FUSEAU à la création, jamais saisi. Une clé technique
(séquence) reste en base pour les jointures. Pour la reprise du gsheet, les
artworks existants reçoivent la date de demande, ou à défaut la date de dernière
version.

### 2.3 Prototypes sans référence Sylob (appel de Clarisse, 08/10, à trancher)

Prise de note d'Antho, appel avec Clarisse :

- Pour un article qui n'existe pas encore, Clarisse veut un **numéro
  d'identifiant du « prototype »** : pas encore de référence Sylob, et la
  désignation peut changer.
- Ce numéro sert à suivre le **projet / prototype** de bout en bout.
- Le commerce fait une demande de création d'artwork. À ce stade, il s'agit
  d'un **échantillon**, pas d'un article.
- Clarisse, ou le commerce directement, crée une **demande, un peu comme un ticket**.

Constat dans le gsheet (onglet « Artworks en attente », 08/10) : 9 lignes sur 10
sont « PAS DE REF » ou « REF À CRÉER ». Le cas sans référence est donc le cas
courant des demandes en cours, pas une exception.

Conséquence sur le §2.2 : l'ID « article + date » ne tient pas pour ces lignes.
Le préfixe `NOUVEAU-AAAAMMJJ` prévu pour elles est un pis-aller : plusieurs
prototypes créés le même jour ne se distinguent que par un suffixe -2, -3, et
l'ID ne change pas quand la référence Sylob arrive.

Piste à valider avec Clarisse :

- un **numéro de demande** attribué à la création, indépendant de l'article
  et de la désignation, par exemple `AW-2026-0001` ;
- la référence Sylob est **rattachée plus tard**, à sa création, sans changer
  le numéro ; la désignation reste modifiable, historisée par le journal ;
- question ouverte : ce numéro remplace-t-il l'ID « article + date » pour
  **tous** les artworks (un seul format, plus simple), ou seulement pour les
  prototypes ?
- statut supplémentaire `demande` (ticket ouvert par le commerce) avant
  `en_attente` ? Les commerciaux devraient alors accéder à FUSEAU. L'app
  registration accepte déjà tout utilisateur du tenant, mais c'est à valider.
- lien possible avec le classeur Drive « 2026 Maison et Objet Suivi des
  échantillons », qui suit déjà les échantillons demandés, dont des lignes
  « PAS DE REF ».

Tant que ce point n'est pas tranché, ne pas appliquer `sql/20261008_socle_ecriture.sql`
ni lancer la reprise : la forme de l'identifiant est figée à la création.

## 3. Modèle de données cible (option A)

Nouvelle table `achat.artwork_version` (nom à confirmer), alimentée par les
saisies, jamais rechargée en full-refresh :

| Colonne | Rôle |
|---|---|
| `id` | identité, séquence native |
| `code_article` | article (un article, plusieurs artworks) |
| `rang` | rang de l'artwork pour l'article, sert au code lisible |
| `statut` | `en_attente`, `valide`, `archive` |
| `cree_le`, `valide_le`, `archive_le`, `maj_le` | les trois dates demandées, plus l'archivage |
| `valideur`, `priorite`, commentaires | repris du gsheet |
| `lien_drive` | lien du PDF |
| `cree_par`, `maj_par` | identité Entra |

- Tableau « en attente » = `statut = 'en_attente'` ; « archive » = `valide` et `archive`.
- Automatisation du point 6 : passage `valide` → `archive` par une action de
  Maxence dans FUSEAU, ou automatique après un délai, à fixer avec lui.
- `achat.v_artwork` est réécrite sur la nouvelle table : la Fiche Article et
  les KPI continuent de fonctionner.
- Reprise : les 393 lignes du gsheet sont importées une fois. Les 8 « en
  attente » deviennent `en_attente`, les 385 « Liste artworks » deviennent
  `valide` (ou `archive`, à trancher). L'ETL `transform_artwork` est retiré
  de l'ordonnancement après la reprise, et annoté « NE PAS ORDONNANCER ».
- Droits : le rôle `dtpf_fuseau_api_prod` a déjà INSERT et UPDATE sur
  `artwork_statut`. Il lui faudra les mêmes droits sur la nouvelle table
  (migration à faire valider).

## 4. Hors périmètre de ce lot

- Accès de Clarisse : groupe ou affectation Entra sur l'App Service, à faire par l'IT.
- Contrôle de l'artwork fournisseur (point 8) : chantier à part. Piste à
  évaluer : OCR et lecture des codes-barres sur le PDF, puis comparaison champ
  par champ. Une première étape réaliste : vérifier les EAN, SPCB et PCB, car un
  code-barres se lit de façon fiable et c'est l'erreur la plus coûteuse.

## 5. Questions pour Clarisse et Maxence

1. Option A : Clarisse est-elle d'accord pour saisir dans FUSEAU et figer le gsheet ?
2. Les 385 lignes « Liste artworks » sont-elles à classer en validées ou en archivées ?
3. ~~Le passage en archive : action manuelle de Maxence dans FUSEAU, ou automatique après combien de jours ?~~ **Tranché le 08/10 (Antho) : clic manuel de Maxence**, qui vérifie puis lance lui-même la suite de son process.
4. Où sont rangés les PDF sur le Drive, et le lien est-il déjà dans le gsheet ?
   **Réponse de Maxence (08/10) : Drive partagé « Design et Achat »**
   (https://drive.google.com/drive/folders/0AAE8JCcsNJ4wUk9PVA). Rangement par
   marque puis par gamme (TB COLLECTION / SAN REMO…). PDF nommés
   `<réf>-<marque>-<gamme>-<désignation>-<JJ.MM.AAAA>.pdf`. Le gsheet de suivi
   est à la racine de ce Drive. Maxence demande d'ajouter le lien de l'artwork à
   valider. Proposition : un champ lien collé par Clarisse.
5. Qui d'autre que Clarisse doit pouvoir créer ou valider un artwork ?
   **Réponse de Maxence (08/10) :** c'est lui qui fait le plus d'actions sur le
   fichier ; Clarisse doit aussi pouvoir modifier, **sauf l'archivage (la
   « descente »), réservé à Maxence**. Appel de Clarisse : le commerce pourrait
   créer lui-même une demande (§2.3).
6. Les artworks en attente qui « dorment » : **réponse de Maxence (08/10)**,
   ils restent en attente tant qu'il n'y a pas de commande ; certains sont
   d'actualité, d'autres non, et on ne le sait que lorsqu'il met à jour le
   tableau et que Clarisse dit OK. Proposition : afficher « commande en cours »
   calculé à partir des commandes ouvertes Sylob, sans rien à saisir.
