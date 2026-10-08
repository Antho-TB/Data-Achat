# Prompt pour la session Claude du poste de Marlène, cinquième passage (préparé le 08/10/2026)

> Fait suite au compte rendu du quatrième passage (08/10) et aux PR #47 à #49
> (`main` = `017b085`, 325 tests). Priorité : mettre le poste sur le pull
> fiabilisé (PR #47) et vérifier qu'il tient. À coller tel quel dans la session
> Claude du poste de Marlène.

---

```text
Cinquième passage sur le poste de Marlène, dépôt C:\Users\mmontbrizon\Documents\Claude\Data-Achat.
Garde-fous du premier passage, toujours valables (docs\20261005_FUSEAU_Prompt_SessionPosteMarlene_v1.md) : rien sur le réseau, le VPN, le pare-feu ou Azure (Samuel est absent, l'IP de DTPF ne doit pas bouger) ; aucune écriture en base (requêtes de contrôle en SET TRANSACTION READ ONLY) ; pas de commit, pas de push ; ne jamais afficher un secret ; ne jamais modifier un document partagé (IMPORT, gsheets) : lecture seule. Ne crée JAMAIS config\facture_auto.flag.
Seules modifications autorisées : le git pull de l'étape 2 ; les fichiers de travail que tu crées dans %TEMP% ; la copie du prompt Cowork vers FUSEAU_retours (étape 4) ; la suppression des fichiers listés à l'étape 7, et d'aucun autre.
Compte rendu : C:\Users\mmontbrizon\Documents\Claude\FUSEAU_retours\<AAAAMMJJ du jour>_CR_SessionPoste_v5.md, et colle son contenu complet dans ta réponse finale.

ÉTAPE 1 : ÉTAT DES LIEUX ET PULL DE CE MATIN
a. Pour FUSEAU_Files_ETL, FUSEAU_Daily_ETL, FUSEAU_Gmail_ETL : dernier run, dernier résultat, prochain run.
b. git rev-parse --short HEAD, git fetch origin main, git rev-parse --short origin/main, git status --porcelain.
c. Dans deploy\logs\etl_files_<AAAAMMJJ>.log et logs\daily_etl_<AAAAMMJJ>.log du jour (et de chaque jour depuis le 09/10 s'il y en a plusieurs) : recopie les lignes du pull (HEAD avant, distant, retard, [SUCCES] ou [ATTENTION], HEAD après) et l'heure de début de chaque tâche. Le 08/10, le pull avait annoncé « [SUCCES] f43f1cd -> f43f1cd » sans rien fusionner : dis-moi si c'est arrivé de nouveau (HEAD après = HEAD avant alors que le retard était > 0).
d. Existe-t-il deploy\logs\PULL_BLOQUE.txt ou deploy\logs\pull.lock ? Si oui, recopie leur contenu et leur date de modification.

ÉTAPE 2 : MISE À JOUR DU CODE (PRIORITAIRE)
Le pull automatique a été réécrit (PR #47) : un seul point de pull, src\utils\git_sync.py, sous verrou. Tant que le poste n'a pas ce code, c'est l'ancien pull, fragile, qui tourne à chaque démarrage.
a. Seulement si git status --porcelain (fichiers suivis) est vide : git pull --ff-only origin main. Attendu : 017b085 ou plus récent. Si le pull refuse, n'insiste pas : note la sortie et les fichiers en cause, et saute l'étape 3.
b. .\.venv311\Scripts\python.exe -m pytest src/tests -q -p no:cacheprovider : nombre de tests (325 attendus sur 017b085), échecs avec leur message.

ÉTAPE 3 : VÉRIFIER LE NOUVEAU PULL (sans écriture en base)
a. .\.venv311\Scripts\python.exe -m src.utils.git_sync --origine controle_v5, puis $LASTEXITCODE. Attendu : « Deja a jour », exit 0, ni pull.lock ni PULL_BLOQUE.txt dans deploy\logs après coup.
b. Test de concurrence, comme au démarrage du poste : lance trois fois la même commande en parallèle (Start-Process, --origine concurrent_1, _2, _3, sortie de chacune redirigée vers un fichier de %TEMP%). Recopie les trois sorties. Attendu : les trois finissent en exit 0, au moins une affiche « Un autre pull est en cours, attente du verrou... » ou les trois « Deja a jour », et aucun pull.lock ne reste.
c. Ne lance AUCUNE des tâches planifiées FUSEAU_* pour ce test : Files_ETL recharge achat.commande en pleine journée.

ÉTAPE 4 : PROMPT DE LA TÂCHE COWORK fuseau-gmail-threads-achat
a. Copie le SKILL.md de la tâche (celui corrigé le 08/10, pas le .bak) vers C:\Users\mmontbrizon\Documents\Claude\FUSEAU_retours\<AAAAMMJJ>_SKILL_fuseau-gmail-threads-achat.md, sans rien y changer, et donne son hash SHA-256. Antho le versionnera dans le dépôt.
b. Liste ses exécutions depuis le 08/10 12:05 (succès, échec, demande d'autorisation en attente) et, pour chacune, le nombre de fils trouvés par la recherche a) (libellés 01-fournisseurs-…).
c. DEKRA : y a-t-il eu des devis reçus depuis le 08/10 (expéditeur @dekra.com, objet « FRI ») ? En lecture seule : SELECT count(*), max(created_at) FROM achat.qualite_decision WHERE decision = 'reservee'. S'il y a un devis mais aucune ligne « reservee », explique pourquoi la tâche ne l'a pas capté.

ÉTAPE 5 : « Payé ? » ET DATES 1970 (lecture seule)
a. Fichier IMPORT, même ouverture qu'au passage du 08/10 (pipeline._find_file(Config.DATA_DIR, "import"), onglet « IMPORT 2026 », en-tête ligne 4, openpyxl read_only=True, data_only=True, jamais enregistré). Date de dernière modification du fichier, puis valeur brute et type de « Payé ? » pour : PO 00017753 (TJKY), PO 00018180 (Julia le 08/10), PO 00018132 (acompte OUI), ligne du PO « NA » MOULE BLOC ALU (46282 le 08/10). Dis pour chacune si elle a changé depuis le 08/10.
b. Hypothèse à confirmer en base : avant la PR #48, une date tapée comme un nombre partait au 01/01/1970. En lecture seule, dans achat.commande : pour chaque colonne date (date_paiement, date_commande, date_statut, etd_confirme, etd_reel, eta, date_livraison), nombre de lignes avec une valeur antérieure au 01/01/2000, et le détail (po_number, code_article, colonne, valeur). Précise si le dernier FUSEAU_Files_ETL a tourné avant ou après ton pull de l'étape 2 : seul un run sur 017b085 ou plus récent corrige ces lignes.

ÉTAPE 6 : FACTURES FOURNISSEURS, DRY-RUN DU TRI (aucune activation, aucune écriture en base)
Le passage du 08/10 a proposé une requête Gmail (rappel 44/44, précision ≈ 61 %). Avant toute activation, il faut savoir si le tri préalable (src\scripts\gmail\triage_piece.py) écarte les faux positifs : PO signés, relances, réclamations.
a. N'utilise PAS fetch_attachments : il dépose dans data\PJ, que relit parse_bl dans FUSEAU_Gmail_ETL, et des factures y seraient prises pour des BL.
b. Télécharge en lecture seule, avec un script de travail dans %TEMP% qui réutilise src.utils.google_auth, les pièces jointes des fils renvoyés par cette requête, bornée au 09/08-08/10/2026, vers %TEMP%\fuseau_factures_tri\<id du fil>\ :
   has:attachment after:2026/08/09 before:2026/10/09 from:(debbie@tb-groupe.fr OR susanna@tb-groupe.fr OR julia@tb-groupe.fr OR sunlordinc.com OR dakoohome.com) ("attached invoice" OR "attached invoices" OR "attached credit note" OR "attached PI" OR "attached signed PI" OR "the P.I." OR filename:invoice OR filename:inovice OR filename:credit OR filename:PI OR filename:CI OR filename:proforma)
c. .\.venv311\Scripts\python.exe -m src.scripts.gmail.triage_piece --folder %TEMP%\fuseau_factures_tri --out %TEMP%\fuseau_factures_tri.json. N'appelle ni parse_facture ni load_facture (appels au modèle, écriture en base).
d. Tableau croisé : pour chaque pièce, ta lecture (facture, note de crédit, PI, PO signé, autre) contre la décision du tri (a_analyser ou écarté, étage, motif). Compte : vraies pièces comptables écartées à tort (le chiffre qui compte), faux positifs laissés « a_analyser », total. Signale les .jpg et .xls (GUANGWEI, MINGHAO).

ÉTAPE 7 : NETTOYAGE
Supprime dans %TEMP%, s'ils existent, les fichiers de travail du passage du 08/10 : fuseau_import_paye.py, fuseau_nondate.py, fuseau_nondate.md, fuseau_q_artwork.py, fuseau_runs.py, fuseau_runs*.txt, fuseau_edit_skill2.py, fuseau_daily_tail.txt. Garde ceux de ce passage, dont %TEMP%\fuseau_factures_tri et son JSON, et liste-les dans le compte rendu.

ÉTAPE 8 : COMPTE RENDU
Tableau de synthèse en tête (étape, état OK / KO / non fait, une ligne), puis une section par étape : fait, chiffres, échecs avec message exact, non fait et pourquoi. Ne conclus pas « tout est OK » sans les chiffres. Termine par la liste des points à remonter à Antho.
```

---

## Ce qu'Antho fait ensuite

- Étape 2 réussie (le poste a la PR #46) : exécuter `sql/20261008_dedoublonnage_qualite_decision.sql` (`docs/plan_action.md` §3.10, « Décisions qualité des mails »).
- Étape 3 : si un pull reste bloqué ou si un `pull.lock` traîne, corriger `src/utils/git_sync.py` avant le démarrage suivant.
- Étape 4 : versionner le `SKILL.md` de la tâche Cowork dans le dépôt.
- Étape 5 : si des dates 1970 restent en base après un `FUSEAU_Files_ETL` sur le nouveau code, chercher l'autre chemin d'écriture ; relancer Marlène sur les cellules « Payé ? » non corrigées.
- Étape 6 : selon les pièces écartées à tort, ajuster `triage_piece.py` ou décider de l'activation des factures (requête, rattrapage, flag).
