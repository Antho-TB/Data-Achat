# Prompt pour la session Claude du poste de Marlène (05/10/2026)

> À coller tel quel dans une session Claude Code ouverte sur le poste de Marlène,
> dossier `C:\Users\mmontbrizon\Documents\Claude\Data-Achat`.
> **Prérequis côté Antho, avant de lancer la session :** les PR suivantes
> doivent être mergées sur `main` : réceptions Sylob, ETA Gmail, garde-fou OAuth,
> auto-pull, Promo/Opé, Fiche Achat. Sinon l'étape 2 ne ramène pas le bon code.
> **L'étape 3 exige Marlène devant l'écran** (consentement Google dans le navigateur).

---

```text
Tu interviens sur le poste de Marlène MONTBRIZON (Responsable Achats, TB Groupe), dans le dépôt FUSEAU :
C:\Users\mmontbrizon\Documents\Claude\Data-Achat

Contexte : l'application web FUSEAU tourne sur Azure. Ce poste ne fait tourner QUE l'ETL et le pipeline Gmail (tâches planifiées FUSEAU_Files_ETL, FUSEAU_Daily_ETL, FUSEAU_Gmail_ETL et la tâche Cowork fuseau-gmail-threads-achat). L'API locale (FUSEAU-API) est arrêtée volontairement : ne la relance pas.
Lis d'abord CLAUDE.md et AGENTS.md à la racine du dépôt. La source de pilotage est docs/plan_action.md.

GARDE-FOUS, NON NÉGOCIABLES
- Lecture, inspection, dry-run : autorisés sans demander.
- INTERDIT : toucher au réseau, au VPN Stormshield, au pare-feu, aux cartes réseau, ou à quoi que ce soit côté Azure (serveur PostgreSQL, redémarrage, SKU). Samuel (Nubo) est en arrêt prolongé : si l'IP de DTPF ou le tunnel VPN bouge, personne ne pourra le rétablir.
- INTERDIT : DROP, TRUNCATE, DELETE, UPDATE de masse en base, git push, git commit, git reset --hard, suppression de fichiers. En cas de doute : tu t'arrêtes et tu le notes dans le compte rendu.
- Le fichier config\.env contient des secrets : ne jamais afficher ni recopier une valeur de secret. Avant de le modifier, sauvegarde-le en config\.env.bak_20261005 (ce motif est ignoré par git).
- Ne modifie jamais un document partagé avec un tiers (gsheet transitaire, Drive qualité) : lecture seule.
- N'écris rien dans le dépôt en dehors de config\.env. Le compte rendu et les exemples vont dans C:\Users\mmontbrizon\Documents\Claude\FUSEAU_retours\ (crée le dossier s'il manque).

ÉTAPE 1 : ÉTAT DES LIEUX, avant toute modification
a. Pour chacune des tâches FUSEAU_Files_ETL, FUSEAU_Daily_ETL, FUSEAU_Gmail_ETL : dernier run, dernier résultat (code hexadécimal) et prochain run (Get-ScheduledTaskInfo).
b. git status --porcelain, git rev-parse --short HEAD, git fetch puis git rev-parse --short origin/main. Combien de commits de retard ?
c. Les journaux des 7 derniers jours dans deploy\logs\ et logs\ : relève chaque [ERREUR], [ECHEC], [SKIP], ainsi que la dernière ligne « FIN ETL Gmail OK ».
d. Tâche Cowork fuseau-gmail-threads-achat : est-elle active ? À quand remonte son dernier run réussi ?
e. Le fichier config\facture_auto.flag existe-t-il ? (La table des montants de facture est vide en base : je veux savoir si l'étape a seulement tourné une fois.)
f. Combien de fichiers dans data\PJ et dans le sous-dossier du mois courant ?

ÉTAPE 2 : MISE À JOUR DU CODE
git pull --ff-only origin main. Si le pull refuse, n'insiste pas, ne force rien : note la sortie git et les fichiers en cause, puis passe à l'étape 3.
Ensuite, lance .\.venv311\Scripts\python.exe -m pytest src/tests -q et note le résultat (nombre de tests, échecs).

ÉTAPE 3 : RECONSENTEMENT GOOGLE (3 scopes), AVEC MARLÈNE
Le code demande désormais gmail.readonly, drive.readonly et spreadsheets.readonly. Un token qui n'en porte que deux fait échouer le pipeline (c'est ce qui l'a tué du 22/07 au 06/08).
a. Lance d'abord .\.venv311\Scripts\python.exe -m src.scripts.gmail.preflight_gmail et note le code de sortie : 0 = OK, 3 = consentement requis, 1 = autre panne.
b. Seulement si le code vaut 3, et avec Marlène devant l'écran :
   Move-Item config\token.json config\token.json.bak -Force
   .\.venv311\Scripts\python.exe -m src.scripts.gmail.fetch_attachments --dry-run
   Marlène se connecte avec la boîte achat.import@tb-groupe.fr et accepte les 3 autorisations.
c. Relance preflight_gmail : le code de sortie attendu est 0.

ÉTAPE 4 : BASCULE DU SUIVI MARITIME SUR LE GSHEET DU TRANSITAIRE
Consigne détaillée : docs\20261005_FUSEAU_Consigne_PosteMarlene_GsheetMaritime_v1.md. Suis-la. En résumé :
a. Sauvegarde config\.env, puis mets SUIVI_MARITIME_PATH=gsheet et SUIVI_MARITIME_PATH_FICHIER=<le chemin serveur qui était dans SUIVI_MARITIME_PATH>.
b. Lance .\.venv311\Scripts\python.exe -m src.scripts.etl.pipeline --dry-run. Le journal doit indiquer une lecture depuis le gsheet, et non un repli sur le fichier. Relève le nombre de conteneurs et le nombre de conteneurs avec un BL.
c. Pas d'ETL en écriture : la prochaine exécution planifiée (02h00) fera le chargement.

ÉTAPE 5 : RÉCEPTIONS SYLOB (lecture seule)
.\.venv311\Scripts\python.exe -m src.scripts.etl.enrich_reception_sylob --dry-run
Relève la source utilisée (sylob ou myreport), le nombre de réceptions par société, le nombre de lignes rapprochées et le nombre d'homonymies rejetées. N'exécute PAS sql\20261005_reception_grain_article.sql : c'est Antho qui le fera.

ÉTAPE 6 : MAILS DEKRA DE RÉSERVATION D'INSPECTION (lecture seule)
DEKRA envoie à la boîte achat.import@tb-groupe.fr un mail de réservation d'inspection, 2 à 7 jours avant l'inspection. Aucun pipeline ne le capte aujourd'hui. Il servira à afficher « Inspection en cours » avec sa date sur le suivi de commande, et la date d'inspection réservée sur l'onglet Qualité.
a. Dans Gmail (connecteur de la session ou interface web), cherche sur les 90 derniers jours les mails de DEKRA ou les mails qui parlent de réservation ou de booking d'inspection (essaie aussi « inspection booking », « confirmation of inspection », « inspection date »).
b. Choisis 5 exemples récents et variés. Pour chacun, relève : expéditeur (domaine seulement), objet, date d'envoi, date d'inspection annoncée, et la façon dont sont donnés le n° de PO, le fournisseur, l'usine, le n° de réservation ou de rapport DEKRA (format CA…) et les articles. Précise si l'information est dans le corps du mail ou dans une pièce jointe (type de fichier).
c. Écris le tout dans FUSEAU_retours\20261005_Exemples_MailDekraReservation.md. Ne recopie ni signature ni numéro de téléphone.
d. Dis-moi si ces mails passent déjà par la tâche Cowork fuseau-gmail-threads-achat. Si oui, que fait-elle de ces mails ? Si non, pourquoi ?

ÉTAPE 7 : COMPTE RENDU
Écris FUSEAU_retours\20261005_CR_SessionPoste.md avec une section par étape, dans cet ordre :
- ce qui a été fait ;
- les chiffres relevés ;
- ce qui a échoué, avec le message exact ;
- ce qui n'a PAS été fait, et pourquoi.
En tête, mets un tableau de synthèse : une ligne par étape, état OK / KO / non fait.
Si tu as dû t'arrêter sur un garde-fou, dis-le explicitement. Ne conclus pas « tout est OK » sans les chiffres qui le prouvent.
```

---

## Ce qu'Antho fait de son côté

- Merger les PR, puis vérifier que `/api/health` sert le nouveau commit.
- Faire appliquer `sql/20261005_default_privileges_myreport_fuseau.sql` sous le compte `dtpf_sylob_myreport_prod`, sinon la recherche article et l'onglet Promo/Opé continuent de passer sur leur repli.
- Après le premier ETL nocturne sur le nouveau code, appliquer `sql/20261005_reception_grain_article.sql`.
- Récupérer `FUSEAU_retours\` sur le poste pour écrire le parseur DEKRA.
