# Prompt pour la session Claude du poste de Marlène, troisième passage (07/10/2026)

> À coller tel quel dans la session Claude Code du poste de Marlène, **le 07/10 après
> 02h** (le pull automatique de `FUSEAU_Files_ETL` doit avoir ramené `47eebc1` ou plus récent).
> **Marlène devant l'écran** pour l'étape 2 si Google redemande le consentement.
> Décision d'Antho du 06/10 : activer les montants de facture.

---

```text
Troisième passage sur le poste de Marlène, dépôt C:\Users\mmontbrizon\Documents\Claude\Data-Achat. Mêmes garde-fous que les passages précédents (relis-les dans docs\20261005_FUSEAU_Prompt_SessionPosteMarlene_v1.md), avec ces précisions :
- Modifications autorisées : config\.env (sauvegarde préalable en config\.env.bak_20261007) et création de config\facture_auto.flag. Rien d'autre dans le dépôt.
- Écritures en base autorisées UNIQUEMENT par les modules du dépôt cités ci-dessous (load_facture sans --dry-run, tâche FUSEAU_Files_ETL). Aucune requête SQL écrite à la main.
- Rien sur le réseau, le VPN, Azure. Pas de commit, pas de push, pas de suppression.
Compte rendu dans C:\Users\mmontbrizon\Documents\Claude\FUSEAU_retours\20261007_CR_SessionPoste_v3.md, et colle son contenu complet en fin de session.

ÉTAPE 0 : PRÉREQUIS
a. git rev-parse --short HEAD : doit contenir le commit 2e89ff9 (git merge-base --is-ancestor 2e89ff9 HEAD). Sinon : git status --porcelain, relève pourquoi le pull n'est pas passé (deploy\logs\PULL_BLOQUE.txt) et ARRÊTE-TOI.
b. Get-ScheduledTaskInfo des 3 tâches FUSEAU_* : dernier run et résultat.

ÉTAPE 1 : RELIRE LES COMPTES RENDUS PRÉCÉDENTS
Lis FUSEAU_retours\20261005_CR_SessionPoste.md et 20261005_CR_SessionPoste_v2.md. Recopie dans ton compte rendu : ce qui avait été fait ou non pour la bascule maritime (étape 4 du v1) et pour les factures (étape 4 du v2), avec les messages d'erreur exacts.

ÉTAPE 2 : BASCULE DU SUIVI MARITIME SUR LE GSHEET
Suis docs\20261005_FUSEAU_Consigne_PosteMarlene_GsheetMaritime_v1.md (sauvegarde en .bak_20261007 au lieu de .bak_20261005). Si l'étape 1 montre que c'est déjà fait, vérifie seulement la valeur des deux variables (sans afficher de secret) et passe au test.
Depuis le 06/10, un gsheet illisible retombe bien sur le fichier serveur (correctif 2e89ff9) : en cas d'échec de lecture, laisse SUIVI_MARITIME_PATH=gsheet et SUIVI_MARITIME_PATH_FICHIER renseigné, relève l'erreur exacte, et n'insiste pas.
Après FUSEAU_Files_ETL : relève dans le journal la ligne « SUIVI MARITIME lu depuis le gsheet » ou « repli sur le fichier serveur », et le nombre de conteneurs.

ÉTAPE 3 : ACTIVATION DES MONTANTS DE FACTURE
a. Contrôles avant activation, tous obligatoires :
   - la clé Gemini est présente (Config.get_gemini_api_key() ne lève pas, sans afficher la valeur) ;
   - la dépendance d'extraction est installée (étape 3 du runbook docs\20260731_FUSEAU_RunbookPosteMarlene_MontantsFacture_v1.md) ;
   - la table achat.facture_fournisseur existe (le module le signale au lancement).
   Si un contrôle échoue : ne crée pas le flag, relève l'erreur, passe à l'étape 4.
b. Dry-run du mois courant : .\.venv311\Scripts\python.exe -m src.scripts.gmail.load_facture --folder data\PJ\202610 --dry-run. Si plus d'un tiers des pièces finissent en [ECHEC], ou si le module plante : ne crée pas le flag, relève, passe à l'étape 4.
c. Rattrapage, chargement réel, un mois à la fois, dans cet ordre : data\PJ\202607, 202608, 202609, 202610 (ceux qui existent), sans --dry-run. Pour chaque mois : pièces chargées, écartées, [ATTENTION] écart (recopie-les), [ECHEC], durée.
d. Crée le fichier vide config\facture_auto.flag (New-Item -ItemType File). À partir de là, FUSEAU_Gmail_ETL charge le mois courant à chaque passage.
e. Relève les 3 cas témoins du runbook (HONGXING 6 403,20 EUR, note de crédit GUANGWEI négative, liasse JIT GLOBAL 19 557,72) : chargés correctement ou non.

ÉTAPE 4 : COMPTE RENDU
Tableau de synthèse en tête (étape, fait / non fait, chiffre clé), puis une section par étape avec les messages exacts. Termine par git status --porcelain (doit être vide).
```

---

## Ce qu'Antho fait ensuite

- Vérifier en base l'origine des lignes de `achat.ot_transport` (gsheet ou fichier serveur) et le retour des BL `SZSE2608065` et `TEMU7385996`.
- Vérifier le volume de `achat.facture_fournisseur` et les écarts facture / IMPORT signalés.
