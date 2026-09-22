# FUSEAU — Qualité de donnée `achat.ot_transport` : anomalies à traiter

**Date :** 2026-09-03
**Origine :** session de fiabilisation du projet `fiche_de_controle` (Scanner Qualité,
service qualité / contrôle réception). Constats faits en LECTURE SEULE sur
`dtpf_sylob_prod`, aucune écriture, aucune correction appliquée.
**Décision liée :** `claude/.ai_memory/decisions_log/20260902_fiche_controle_fiabilisation.md`

## Pourquoi ça concerne FUSEAU

`fiche_de_controle` consomme désormais `achat.ot_transport` et
`achat.ot_transport_bl` en lecture, pour retrouver le contexte de réception d'un
conteneur à partir du **nom de fichier** de la Packing List
(`PL-<BL>-<CONTENEUR>.pdf`). C'est une dépendance unidirectionnelle et
documentée : le domaine qualité lit, il n'écrit jamais dans `achat.*`.
Ces deux tables appartiennent à FUSEAU, donc les corrections lui reviennent.

## Anomalie 1 — La colonne `n_bl` ne contient pas toujours un BL

Elle mélange au moins trois natures de valeur :

| `n_conteneur` | `n_bl` observé | nature réelle |
|---|---|---|
| `RESU2004119` | `00169477` | **numéro de commande d'achat** (8 chiffres, zéros de tête) |
| `YMMU1140160` | `EWAREBC` | **code transitaire**, pas un connaissement |
| `TCNU7363908` | `SZSE2507291` | BL correct |
| `TLLU4162583` | `NULL` | absent |

Conséquence pour un consommateur : un rattachement par `n_bl` est non fiable.
Côté `fiche_de_controle`, le numéro de conteneur a donc été retenu comme clé
discriminante, le BL n'étant qu'un repli explicitement journalisé.

Effet secondaire intéressant : pour `RESU2004119`, le `00169477` stocké dans
`n_bl` **est** le bon PO de la Packing List `PL-SZSE2601807-RESU2004119`. La
donnée conteneur vers commande existe donc bien dans le flux, elle est
simplement rangée dans la mauvaise colonne. Ce serait un vrai gain de la
qualifier proprement.

## Anomalie 2 — `ot_transport_bl` est quasi vide et son `fournisseur` est nul

- 29 lignes dans `achat.ot_transport_bl` contre 147 dans `achat.ot_transport`.
- `source_fichier` vaut `reprise:ot_transport` sur les lignes observées, donc
  elles proviennent d'une reprise et non du flux Gmail courant.
- La colonne `fournisseur` est `NULL` sur tout l'échantillon regardé.

Conséquence : le nom du fournisseur ne peut pas venir du suivi transport. Côté
`fiche_de_controle` il est pris dans `public.fournisseurs2.raison_sociale` via
`commandes_detaillees27.frn_id_fournisseur`, ce qui est de toute façon la source
de vérité ERP. À voir si `ot_transport_bl.fournisseur` a encore une raison
d'exister ou si la colonne doit être retirée plutôt que laissée vide.

## Pistes de correction, à arbitrer par FUSEAU

1. **Typer la valeur à l'ingestion** plutôt que de tout verser dans `n_bl` :
   une colonne `n_bl` réservée aux vrais connaissements, un `po_number` quand la
   valeur correspond à `^\d{8}$` et existe dans `commandes_detaillees27`, un
   `transitaire` quand elle correspond à un code connu. Journaliser en
   `[ATTENTION]` toute valeur non classable au lieu de l'écrire quand même.
2. **Contrainte ou vue de contrôle** listant les `n_bl` non conformes, à
   surveiller après chaque run, pour que la dérive ne réapparaisse pas.
3. **Compléter ou supprimer `ot_transport_bl`** : si le mapping conteneur vers BL
   doit vivre, il faut l'alimenter depuis le flux courant, pas depuis une reprise
   figée. Sinon, mieux vaut le retirer que laisser une table à 20 pour cent de
   couverture que d'autres domaines croiront pouvoir joindre.
4. **Distinguer l'inconnu du vide** dans les restitutions : un `n_bl` nul et un
   `n_bl` faux ne se lisent pas de la même façon côté métier.

## Ce que le prochain run FUSEAU doit vérifier avant de coder

- Le flux Gmail écrit-il encore dans `n_bl` des valeurs non conformes, ou est-ce
  uniquement l'héritage de la reprise du 2026-07-28 ?
- Combien de lignes de `ot_transport` ont un `n_bl` classable en PO, et
  combien de ces PO existent réellement dans `commandes_detaillees27` ?
- Toute correction de masse sur ces tables est un script destructeur : accord
  écrit d'Antho, archivage préalable dans `_archive_ot_transport_<date>`,
  garde-fou de volume, et migration versionnée dans `sql/`.
