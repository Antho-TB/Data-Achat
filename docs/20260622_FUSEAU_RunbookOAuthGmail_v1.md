# FUSEAU -- Runbook OAuth Gmail (Plan A : fetch_attachments)
_2026-06-22 · à exécuter une fois, avant le branchement sur le poste de Marlène_

> Objectif : obtenir `config/credentials.json` (OAuth client desktop) pour que
> `src/scripts/gmail/fetch_attachments.py` puisse lire les PJ.
> Action liee au compte Google, a realiser manuellement dans la console GCP.

## 1. Projet Google Cloud
1. Console : https://console.cloud.google.com → sélectionner (ou créer) un projet
   dédié, ex. `tb-fuseau-achats`.
2. **APIs & Services → Library** → rechercher **Gmail API** → **Enable**.

## 2. Écran de consentement OAuth
3. **APIs & Services → OAuth consent screen** :
   - User type : **Internal** (compte Workspace TB Groupe -- pas de validation Google requise).
   - App name : `FUSEAU Achats`, e-mail support : a.bezille@tb-groupe.fr.
4. **Scopes** : ajouter `.../auth/gmail.readonly` (lecture seule -- le script ne
   demande rien d'autre). Save.

## 3. Identifiant OAuth (client desktop)
5. **APIs & Services → Credentials → Create credentials → OAuth client ID**.
   - Application type : **Desktop app**, nom : `fuseau-fetch-attachments`.
6. **Download JSON** → renommer en `credentials.json` → déposer dans
   `Data-Achat/config/` (déjà gitignoré, ne JAMAIS committer).

## 4. Premier lancement (consentement)
7. Sur le poste qui exécutera le fetch (poste Marlène, VPN actif) :
   ```
   pip install -r requirements-gmail.txt
   python -m src.scripts.gmail.fetch_attachments --dry-run
   ```
8. Un navigateur s'ouvre → se connecter avec **le compte Gmail de Marlène** →
   consentir (lecture seule). Un `config/token.json` est mis en cache : les
   exécutions suivantes (tâche planifiée) ne redemanderont plus de consentement.
9. Le `--dry-run` liste les PJ candidates sans rien écrire. Si la liste est
   cohérente, relancer **sans** `--dry-run` pour télécharger vers `GMAIL_PJ_DIR`.

## 5. Prérequis Gmail côté boîte
- Créer le label **`Achats/Fournisseurs`** (valeur par défaut `GMAIL_LABEL`) et y
  classer les fils fournisseurs (filtre Gmail recommandé : expéditeurs TB China /
  transitaire / fournisseurs → applique le label automatiquement).
- Alternative : changer `GMAIL_LABEL` dans `config/.env` pour un label existant.

## 6. Décisions ouvertes
- **Nom du label** : `Achats/Fournisseurs` proposé -- à valider/créer côté Gmail.
- **Compte ciblé** : Marlène (en copie quasi-systématique). Mesurer le « quasi »
  après branchement : PO de l'IMPORT sans fil retrouvé = trou à combler.
- **Service account + délégation domaine** : alternative au consentement
  interactif (utile pour une tâche planifiée serveur sans navigateur). À étudier
  avec l'IT si on industrialise -- surdimensionné pour le POC.
