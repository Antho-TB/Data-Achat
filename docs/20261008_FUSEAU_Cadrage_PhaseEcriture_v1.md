# FUSEAU : cadrage de la phase d'écriture

> Statut : **socle préparé le 08/10/2026, rien n'est activé en production.**
> L'écriture s'allume domaine par domaine, après la phase de contrôle de la
> qualité et de la fraîcheur des données, par une variable d'environnement et
> une migration SQL appliquée par Antho.

## 1. Ce qui change

Jusqu'ici, FUSEAU **lit** : Sylob (via MyReport), l'IMPORT, les gsheets, les mails.
Les seules saisies sont des annotations sur des lignes existantes (date de
paiement, ETD forcée, commentaire), dans `achat.commande_annotation`.

La phase d'écriture fait de FUSEAU **la source** de données qui n'existent dans
aucun autre système, ou qui sont tenues aujourd'hui dans des gsheets fragiles :

| Domaine | Aujourd'hui | Demain | Qui saisit |
|---|---|---|---|
| Artworks | gsheet `LIS-CON-28-0` de Clarisse, relu chaque matin | Table `achat.artwork_fuseau`, saisie dans FUSEAU, gsheet figé en archive | Clarisse (création, validation), Maxence (archivage) |
| Suivi des analyses | gsheet SUIVI DES ANALYSES, onglets « en attente » et « archives » | Table `achat.analyse_suivi` : urgence, état produit, état analyse, archivage | Maxence, service qualité |
| Facturation intersite | Cases « à facturer » et « facturation faite » du gsheet | Table `achat.facturation_intersite_suivi` ; les montants restent lus dans Sylob | Maxence |
| Paiements, ETD, commentaires | Déjà saisis dans FUSEAU | Inchangé | Achats |

**Règle de source, inchangée :** ce qui existe dans Sylob (ERP) n'est jamais
ressaisi dans FUSEAU. FUSEAU porte uniquement ce qui est hors du circuit ERP.

## 2. Principes du socle (communs à tous les domaines)

1. **Tables persistantes, jamais rechargées.** Les tables saisies dans FUSEAU ne
   sont jamais vidées par un ETL. Aucun chargement nocturne n'y écrit.
2. **Identité tracée.** Chaque création ou modification enregistre l'auteur
   Microsoft 365 (`X-MS-CLIENT-PRINCIPAL-NAME`), déjà transmis par Azure.
3. **Journal des modifications.** Chaque écriture ajoute une ligne à
   `achat.journal_modification` : table, clé, action, valeurs avant et après,
   auteur, date. On sait toujours qui a changé quoi, et on peut revenir en arrière.
4. **Pas de suppression.** On archive (statut + date + auteur). Le rôle de l'API
   n'a pas le droit `DELETE`.
5. **Concurrence optimiste.** Chaque ligne porte une `version`. Une modification
   envoie la version qu'elle a lue ; si quelqu'un a enregistré entre-temps, la
   modification est refusée (HTTP 409) avec un message clair, au lieu d'écraser
   en silence le travail de l'autre.
6. **Activation par domaine.** Chaque domaine a son interrupteur
   (`ECRITURE_ARTWORK=1`…). Éteint, FUSEAU continue de lire l'ancienne source :
   on peut déployer le code avant de créer les tables, et revenir en arrière par
   une ligne de configuration.
7. **Reprise unique, puis gel de l'ancienne source.** Pour chaque domaine, un
   script reprend une fois le contenu du gsheet (en dry-run d'abord), puis le
   gsheet passe en lecture seule. Pas de synchronisation dans les deux sens :
   deux sources qui divergent coûtent plus cher qu'un changement d'outil.

## 3. Ce que le socle livre (branche `feat/socle-ecriture`)

| Élément | Fichier | Rôle |
|---|---|---|
| Migration SQL | `sql/20261008_socle_ecriture.sql` | Journal, tables artwork, analyses, facturation ; droits de l'API sans DELETE |
| Écriture générique | `app/ecriture.py` | Création, modification avec version, archivage, journal, identifiant d'artwork |
| API artworks | `app/artwork_fuseau.py` | Lister, créer, modifier, valider, archiver, historique ; actif si `ECRITURE_ARTWORK=1` |
| Reprise du gsheet | `src/scripts/etl/reprise_artwork_gsheet.py` | Copie unique `artwork_statut` vers `artwork`, dry-run par défaut |
| Interface | `frontend/index.html` | Boutons de saisie de l'onglet Artwork quand l'écriture est active ; gestion des conflits |

Les analyses et la facturation ont leurs tables dans la migration ; leurs écrans
de saisie viendront avec le lot 3 de BUG-007, sur le même socle.

## 4. Mise en route d'un domaine (exemple : artworks)

1. Antho applique `sql/20261008_socle_ecriture.sql` avec son compte nominal.
2. Reprise en dry-run : `python -m src.scripts.etl.reprise_artwork_gsheet`, lecture du rapport.
3. Reprise réelle : même commande avec `--commit`.
4. App setting `ECRITURE_ARTWORK=1` sur la Web App, et redémarrage.
5. Clarisse et Maxence testent sur quelques artworks.
6. Le gsheet de Clarisse passe en lecture seule ; le chargement quotidien du
   gsheet artwork est retiré de `run_daily_etl.ps1`.

Retour arrière : `ECRITURE_ARTWORK=0`. FUSEAU relit le miroir du gsheet, rien
n'est perdu dans la table `achat.artwork_fuseau`.

## 5. Décisions déjà prises

- Identifiant d'artwork : n° d'article + date de création concaténés
  (`32030006-20261008`, suffixe `-2` si deux le même jour, figé à la création).
  Validé par Clarisse le 08/10.
- Archivage des artworks : clic manuel de Maxence, qui vérifie puis lance
  lui-même la suite de son process (Antho, 08/10).
- Archivage des analyses : manuel, une fois l'analyse traitée (Maxence, 08/10).

## 6. Questions ouvertes

1. Artworks sans référence (« PAS DE REF », « REF À CRÉER ») : identifiant
   provisoire `NOUVEAU-<date>`, remplacé quand la référence est créée ? (proposé)
2. Les 384 artworks de la Liste : repris au statut « validé » (proposé), ou
   certains déjà « archivés » ?
3. Qui peut valider un artwork en dehors de Clarisse ? Aujourd'hui, tout
   utilisateur connecté peut écrire ; des rôles Entra (« Design », « Achats »)
   pourront restreindre les actions si besoin.
4. Où sont rangés les PDF des artworks sur le Drive (pour le lien) ?
