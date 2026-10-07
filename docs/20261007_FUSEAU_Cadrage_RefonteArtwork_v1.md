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

La proposition « n° article + date » donne le même identifiant à deux artworks
d'un même article créés le même jour, et change si la date est corrigée.
Proposition : un identifiant technique attribué par la base (séquence), et un
code lisible affiché, du type `ART-32030006-03` (article + rang de l'artwork
pour cet article), calculé et jamais saisi.

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
3. Le passage en archive : action manuelle de Maxence dans FUSEAU, ou automatique après combien de jours ?
4. Où sont rangés les PDF sur le Drive, et le lien est-il déjà dans le gsheet ?
5. Qui d'autre que Clarisse doit pouvoir créer ou valider un artwork ?
