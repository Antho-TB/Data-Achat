# Consigne pour le Claude du poste de Marlène : bascule du suivi maritime sur le gsheet

> Rédigée le 05/10/2026 par le Claude d'Antho. À exécuter sur le poste de Marlène,
> à la racine du dépôt FUSEAU. Plan d'action §3.6 et §3.8.

## Contexte

L'ETL lit encore la copie du suivi maritime sur le serveur
(`2026 SUIVI MARITIME.xlsx`). Cette copie n'a plus de colonne BL : 52 conteneurs
sur 60 arrivent sans n° de BL dans `achat.ot_transport`. C'est la cause des
erreurs de BL signalées par Marlène en démo le 22/09.

La source qui fait foi est le classeur tenu par le transitaire QUALITAIR sur Drive
(id `1hP73oivXrB8o8I7pkrGh7y6nPzn0ccfW`, un `.xlsx`, pas un Google Sheet natif).
Le code sait déjà le lire. Seul le `config\.env` du poste force encore le fichier
serveur.

## Autorisé

Modifier `config\.env` (deux lignes), lancer un test de lecture seule, et lancer
une fois la tâche `FUSEAU_Files_ETL`. Rien d'autre : pas de `git` en écriture,
pas d'autre tâche planifiée, aucune requête SQL en écriture.

## Étapes

1. **Sauvegarder** : copier `config\.env` vers `config\.env.bak_20261005`.

2. **Relever** la valeur actuelle de `SUIVI_MARITIME_PATH`. C'est normalement le
   chemin UNC du fichier serveur.

3. **Modifier `config\.env`** :
   - `SUIVI_MARITIME_PATH=gsheet`
   - `SUIVI_MARITIME_PATH_FICHIER=<la valeur relevée à l'étape 2>`. Si la ligne
     n'existe pas, l'ajouter. Elle est indispensable : en cas d'échec de lecture
     du classeur, l'ETL se rabat sur ce chemin. Sans elle, il tombe en mode
     dégradé et n'a plus de source maritime du tout.

4. **Tester en lecture seule**, sans rien écrire en base :

   ```powershell
   .\.venv311\Scripts\python.exe -c "import logging,sys; sys.path.insert(0,'.'); logging.basicConfig(level=logging.INFO); from src.scripts.etl.extract import extract_suivi_maritime; df = extract_suivi_maritime('gsheet'); print(None if df is None else df.shape)"
   ```

   - **Succès attendu** : un log `[SUCCES] SUIVI MARITIME lu depuis le gsheet : N ligne(s)`,
     puis une forme avec environ 18 colonnes.
   - **Si le log dit `[ATTENTION] Gsheet maritime illisible (...) -- repli sur le fichier serveur`** :
     ne pas lancer l'étape 5. Relever le message d'erreur exact. Les causes probables sont
     un classeur non partagé avec le compte Google de FUSEAU (erreur 404 ou 403) ou un
     token sans le bon scope (`insufficient scope`). Pour un problème de scope, ne pas
     supprimer `token.json` : le reconsentement demande Marlène devant le poste.
     Laisser le `.env` modifié : le repli garde le fonctionnement actuel.

5. **Si l'étape 4 a réussi**, lancer `Start-ScheduledTask -TaskName FUSEAU_Files_ETL`,
   attendre la fin, puis relever `LastTaskResult` (attendu `0`) et les lignes du log
   du jour qui mentionnent `SUIVI MARITIME` ou `BL`.

## Rapport à rendre à Antho

- La valeur relevée à l'étape 2.
- La sortie complète de l'étape 4.
- Le résultat de l'étape 5 (`LastTaskResult` et extrait du log), ou la raison pour
  laquelle elle n'a pas été lancée.
- `git status --porcelain`, qui doit rester vide (`config\.env` est ignoré par git).

Le Claude d'Antho vérifiera ensuite en base que `achat.ot_transport` est alimentée
depuis le gsheet et que les BL sont revenus.
