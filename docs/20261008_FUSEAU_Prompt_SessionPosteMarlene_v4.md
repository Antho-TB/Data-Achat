# Prompt pour la session Claude du poste de Marlène, quatrième passage (08/10/2026)

> **Remplace le prompt v3 du 07/10, à ne pas exécuter** : son étape 3 activait les
> montants de facture, ce que le compte rendu du 06/10 déconseille (aucune facture
> fournisseur dans les pièces jointes, contrôle d'écart cassé jusqu'à la PR #41).
> À coller tel quel dans la session Claude du poste de Marlène.

---

```text
Quatrième passage sur le poste de Marlène, dépôt C:\Users\mmontbrizon\Documents\Claude\Data-Achat.
Ce prompt REMPLACE le prompt v3 du 07/10 : ne l'exécute pas, et en particulier ne crée JAMAIS config\facture_auto.flag.
Garde-fous du premier passage, toujours valables (docs\20261005_FUSEAU_Prompt_SessionPosteMarlene_v1.md) : rien sur le réseau, le VPN, le pare-feu ou Azure (Samuel est absent, l'IP de DTPF ne doit pas bouger) ; aucune écriture en base (requêtes de contrôle en SET TRANSACTION READ ONLY) ; pas de commit, pas de push, pas de suppression ; ne jamais afficher un secret ; ne jamais modifier un document partagé (IMPORT, gsheets) : lecture seule.
Seules modifications autorisées : lancer la tâche planifiée FUSEAU_Daily_ETL (étape 3), et le prompt de la tâche Cowork fuseau-gmail-threads-achat après sauvegarde datée .bak_20261008 (étape 5).
Compte rendu : C:\Users\mmontbrizon\Documents\Claude\FUSEAU_retours\20261008_CR_SessionPoste_v4.md, et colle son contenu complet dans ta réponse finale.

ÉTAPE 1 : ÉTAT DES LIEUX
a. Pour FUSEAU_Files_ETL, FUSEAU_Daily_ETL, FUSEAU_Gmail_ETL : dernier run, dernier résultat, prochain run, et le DÉCLENCHEUR exact de chacune (heure, « au démarrage », délai éventuel). Je soupçonne qu'au démarrage du poste, FUSEAU_Daily_ETL tourne avant que FUSEAU_Files_ETL ait fait le git pull : dis-moi l'heure de début et de fin de chacune ce matin (journaux deploy\logs\).
b. git rev-parse --short HEAD, git fetch, git rev-parse --short origin/main, git status --porcelain.
c. Existe-t-il deploy\logs\PULL_BLOQUE.txt ? Si oui, recopie son contenu.

ÉTAPE 2 : MISE À JOUR DU CODE
git pull --ff-only origin main (attendu : 8b92123 ou plus récent). Si le pull refuse, n'insiste pas : note la sortie et les fichiers en cause. Puis .\.venv311\Scripts\python.exe -m pytest src/tests -q (nombre de tests, échecs).

ÉTAPE 3 : RECHARGER LES ARTWORKS AVEC LE PARSEUR CORRIGÉ
Le parseur du gsheet de Clarisse a été corrigé le 07/10 (PR #36) : l'onglet « Artworks en attente » était ignoré en entier. Ce matin, le chargement a encore tourné avec l'ancien code.
a. Seulement si l'étape 2 a réussi : Start-ScheduledTask -TaskName FUSEAU_Daily_ETL, puis attends sa fin (Get-ScheduledTaskInfo, LastTaskResult).
b. Contrôle en lecture seule dans achat.artwork_statut, sur les lignes du dernier chargement (charge_le à moins de 12 h du maximum) : nombre par statut_artwork. Attendu : environ 10 « En attente » et 384 « Validé ». Liste les « En attente » (code_article, designation, priorite).

ÉTAPE 4 : LA LIGNE TJKY À 53 $ ET LA COLONNE « Payé ? » (lecture seule du fichier IMPORT)
Marlène pense avoir saisi le paiement du PO 17753 (TJKY, article 11400003, 53 $, envoi DHL) dans le fichier IMPORT, mais FUSEAU ne voit aucune date de paiement. L'ETL ne retient dans « Payé ? » que des DATES : un texte (« OUI », « payé », une date tapée en texte) est ignoré sans message.
a. Ouvre le fichier IMPORT que lit l'ETL (même résolution de chemin que src/scripts/etl/pipeline.py, onglet « IMPORT 2026 »), en LECTURE SEULE (pandas ou openpyxl, data_only=True). Ne l'enregistre jamais.
b. Pour la ligne du PO 17753 : recopie la valeur brute de la cellule « Payé ? », son type (date, texte, nombre), et la date de dernière modification du fichier.
c. Liste toutes les lignes dont « Payé ? » est rempli mais n'est pas une date : PO, article, valeur brute. Donne leur nombre total.

ÉTAPE 5 : TÂCHE COWORK fuseau-gmail-threads-achat
a. Liste ses exécutions depuis le 06/10 (succès, échec, demande d'autorisation en attente). Le prompt a changé le 06/10 : signale si un run attend une autorisation d'outil.
b. Le premier passage avait relevé que sa recherche par libellé (label:04-FOURNISSEURS…) ne renvoie rien. Liste les libellés Gmail réels de la boîte achat.import@ qui concernent les fournisseurs, puis corrige la recherche dans le prompt (sauvegarde .bak_20261008 d'abord, diff avant / après dans le compte rendu). Ne change rien d'autre au prompt.
c. Réservations DEKRA : aucune décision « reservee » n'est arrivée en base depuis le 06/10. Cherche dans Gmail (lecture seule) les devis DEKRA reçus depuis le 06/10 (objet « FRI », expéditeur @dekra.com). S'il y en a, explique pourquoi la tâche ne les a pas captés.

ÉTAPE 6 : FACTURES FOURNISSEURS, REPÉRAGE SEUL (aucune activation)
Les factures et notes de crédit fournisseurs arrivent par le bureau de Hong Kong, pas par le transitaire. Pour préparer la décision d'Antho, en lecture seule dans Gmail sur les 60 derniers jours :
a. Combien de mails portent une facture ou une note de crédit fournisseur en pièce jointe, de quels expéditeurs, avec quels libellés Gmail ?
b. Propose la requête Gmail qui les cible sans ramener les factures de fret du transitaire. Ne modifie ni deploy\run_gmail_etl.ps1 ni le flag.

ÉTAPE 7 : COMPTE RENDU
Tableau de synthèse en tête (étape, état OK / KO / non fait, une ligne), puis une section par étape : fait, chiffres, échecs avec message exact, non fait et pourquoi. Ne conclus pas « tout est OK » sans les chiffres.
```

---

## Ce qu'Antho fait ensuite

- Si les 10 artworks en attente sont chargés : appliquer `sql/20261008_socle_ecriture.sql`, reprise en dry-run, puis activation de la saisie (`docs/plan_action.md` §3.11).
- Selon l'étape 1 : corriger l'ordre des tâches au démarrage (pull aussi dans `run_daily_etl.ps1`).
- Selon l'étape 4 : faire signaler par l'ETL les « Payé ? » non lisibles.
- Selon l'étape 6 : décider de la source des factures fournisseurs.
