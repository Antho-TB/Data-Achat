# Runbook poste Marlène — mise en service des montants de facture

> **Pour qui** : la session Claude qui tourne sur le poste de Marlène, avec accès
> au dossier `C:\Users\abezille\dev\Data-Achat` (ou l'emplacement local du dépôt
> sur ce poste) et au réseau bureau.
>
> **Objectif** : appliquer les correctifs du 31/07 et mettre en service la lecture
> des montants de facture, puis renvoyer un compte rendu chiffré à Antho.
>
> **Durée** : 30 à 45 minutes, dont deux étapes qui demandent une action humaine.
>
> **Auteur** : Antho Bezille, 31/07/2026. Répond au mail de Marlène du 29/07
> « 260729 FUSEAU – TEST ONGLET PRÉVISIONNEL – PAIEMENTS ».

---

## Règles à respecter du début à la fin

1. **Ne rien lancer pendant que Marlène paie.** L'étape 5 recharge des données de
   suivi maritime. Lui demander si le moment convient avant de commencer.
2. **Aucune suppression, aucun TRUNCATE, aucun DROP dans ce runbook.** Si une étape
   semble en exiger un, s'arrêter et prévenir Antho.
3. **Ne jamais afficher ni recopier un mot de passe ou une clé API** dans la
   conversation, ni dans un fichier journal.
4. **Toute étape marquée STOP est bloquante** : ne pas enchaîner, écrire à Antho
   avec le message d'erreur exact.
5. Consigner au fur et à mesure les chiffres demandés : le compte rendu final n'a
   de valeur que mesuré, pas décrit.

Le python du projet est celui du venv, jamais le python système :
`.\.venv311\Scripts\python.exe` depuis la racine du dépôt.

---

## Étape 1 — Récupérer le code du 31/07

```powershell
cd <racine du depot Data-Achat sur ce poste>
git status --short
git pull
git log --oneline -5
```

**Contrôle** : les quatre commits suivants doivent apparaître dans le journal.

| Commit | Objet |
|---|---|
| `7c55568` | filtre multi-valeurs, total de sélection, provenance des montants |
| `1241c80` | numéros de BL et déblocage de la saisie de paiement |
| `0fadf7d` | création de `achat.facture_fournisseur` |
| `aaf1370` | lecture du montant des factures dans les pièces jointes |

**STOP** si `git status` montrait des fichiers modifiés localement avant le `pull` :
ne pas les écraser, lister les fichiers concernés et prévenir Antho. Le poste est
censé être en lecture seule côté code, un fichier modifié localement signifie que
quelqu'un a édité en direct.

---

## Étape 2 — Créer la table des pièces comptables

Migration additive et rejouable : elle crée `achat.facture_fournisseur`, ses index
et ses contraintes. Elle ne touche à aucune table existante.

```powershell
.\.venv311\Scripts\python.exe -c "from app.database import get_engine; from sqlalchemy import text; from pathlib import Path; e=get_engine(); c=e.connect(); t=c.begin(); c.execute(text(Path('sql/20260731_facture_fournisseur.sql').read_text(encoding='utf-8'))); t.commit(); print('[SUCCES] migration appliquee')"
```

**Contrôle** :

```powershell
.\.venv311\Scripts\python.exe -c "from app.database import get_engine; from sqlalchemy import text; print([dict(r) for r in get_engine().connect().execute(text(\"SELECT COUNT(*) AS colonnes FROM information_schema.columns WHERE table_schema='achat' AND table_name='facture_fournisseur'\")).mappings()])"
```

Résultat attendu : **19 colonnes** (valeur vérifiée le 31/07 en appliquant la
migration dans une transaction annulée). Zéro colonne signifie que la migration n'a
pas été appliquée.

---

## Étape 3 — Installer la dépendance d'extraction

```powershell
.\.venv311\Scripts\python.exe -m pip --version
```

**Si la commande répond `No module named pip`** (c'était le cas sur le poste
d'Antho, ce venv a perdu pip) :

```powershell
.\.venv311\Scripts\python.exe -m ensurepip --upgrade
```

Puis :

```powershell
.\.venv311\Scripts\python.exe -m pip install -r requirements-gmail.txt --disable-pip-version-check
.\.venv311\Scripts\python.exe -c "from google import genai; print('[SUCCES] google-genai disponible')"
```

---

## Étape 4 — Clé Gemini (action humaine, Antho fournit la valeur)

L'extraction des montants a besoin d'une clé Gemini. Deux voies, la première est
préférable.

**Voie Key Vault**, à exécuter par Antho ou par Samuel, une seule fois :

```powershell
az keyvault secret set --vault-name kv-dtpf-prod --name GEMINI-API-KEY --value <cle fournie par Antho>
```

**Voie fichier local**, si le Key Vault n'est pas accessible depuis ce poste :
ajouter dans `config\.env` la ligne `GEMINI_API_KEY=<cle>`.

Ne pas demander la clé à Marlène, ne pas l'afficher, ne pas la recopier dans le
compte rendu.

**Contrôle** :

```powershell
.\.venv311\Scripts\python.exe -c "from src.utils.config_manager import Config; print('[SUCCES] cle disponible' if Config.get_gemini_api_key() else '[ECHEC] aucune cle')"
```

**STOP** si aucune clé : les étapes 1, 2, 3, 5 et 7 restent valables et utiles.
Passer l'étape 6 et le signaler dans le compte rendu.

---

## Étape 5 — Rétablir les numéros de BL (le bug n° 1 de Marlène)

**Cause du problème** : le poste lit la copie serveur du suivi maritime,
`2026 SUIVI MARITIME.xlsx`, qui a perdu sa colonne BL en juillet 2026. Le
chargement se déroulait sans erreur en remplissant la base avec des BL vides. Le
classeur Google du transitaire, lui, porte toujours le BL.

**Mesure AVANT, à consigner** :

```powershell
.\.venv311\Scripts\python.exe -c "from app.database import get_engine; from sqlalchemy import text; print([dict(r) for r in get_engine().connect().execute(text('SELECT COUNT(*) AS conteneurs, COUNT(n_bl) AS avec_bl, MAX(charge_le)::text AS dernier FROM achat.ot_transport')).mappings()])"
```

Relevé sur le poste d'Antho le 31/07 au matin : 146 conteneurs, 36 avec un BL.

> ⚠️ **Corrigé le 06/08 — cette bascule n'est plus à faire.** La mesure sur le
> poste a montré qu'aucune ligne `SUIVI_MARITIME_PATH` n'existe dans le
> `config\.env`, et que le défaut du code est déjà `gsheet`
> ([config_manager.py](../src/utils/config_manager.py)). La bascule était donc
> déjà effective : ce n'était pas la configuration qui bloquait.
>
> La vraie cause était double. Le classeur du transitaire est un **`.xlsx`
> déposé dans Drive**, pas un Google Sheet natif, et l'API Sheets refuse un
> fichier Office. Cet échec était ensuite avalé par le `except` large de
> [extract.py](../src/scripts/etl/extract.py), qui repliait en silence sur la
> copie serveur à 14 colonnes, celle qui n'a pas de colonne BL. Corrigé par
> `lire_classeur()`. **Ne pas modifier `config\.env`**, passer directement à la
> vérification ci-dessous.

<details>
<summary>Instruction d'origine du 31/07, conservée pour mémoire (ne pas appliquer)</summary>

Dans `config\.env`, remplacer la ligne `SUIVI_MARITIME_PATH=...` par les deux
lignes suivantes. Conserver l'ancien chemin comme repli, ne pas le supprimer.

```
SUIVI_MARITIME_PATH=gsheet
SUIVI_MARITIME_PATH_FICHIER=\\192.168.102.55\partage\ADA\METIER\SUIVI CDES IMPORT\2026\TRANSITAIRE\2026 SUIVI MARITIME.xlsx
```

</details>

**Vérifier que le classeur est lisible avant de lancer quoi que ce soit** :

```powershell
.\.venv311\Scripts\python.exe -c "from src.scripts.etl.transform_maritime import GSHEET_MARITIME_ID, _read_rows_gsheet, resoudre_colonnes; l=_read_rows_gsheet(GSHEET_MARITIME_ID); e=[str(c) for c in l[0]]; print('lignes', len(l)); print('entete', e); print('colonne BL a l index', resoudre_colonnes(e).get('bl'))"
```

Trois issues possibles :

- **La colonne BL a un index et des BL apparaissent** : continuer.
- **`credentials.json introuvable`** : les secrets Google manquent sur ce poste,
  **STOP**, prévenir Antho.
- **`Classeur inaccessible` ou scope insuffisant** : supprimer `config\token.json`
  puis relancer la commande, un reconsentement Google s'ouvrira dans le navigateur
  et devra être accepté avec le compte Google de FUSEAU. Vérifier aussi que le
  classeur « SUIVI MARITIME TARRERIAS 2026 » est bien partagé avec ce compte. Si
  le reconsentement échoue, **STOP**.

**Relancer l'ETL maritime**, puis reprendre la mesure AVANT à l'identique pour
obtenir la mesure APRÈS. Le nombre de conteneurs `avec_bl` doit augmenter
nettement. S'il ne bouge pas, la bascule n'a pas pris effet : vérifier que le
`.env` a bien été enregistré et que l'ETL a été relancé après.

**Contrôle métier, le plus parlant** : ouvrir l'onglet Prévisionnel, tableau
« B/L en attente ou bloqués », et compter combien de lignes affichent encore un
tiret dans la colonne N° BL. Avant la bascule, 20 blocs sur 21 n'avaient aucun BL.

---

## Étape 6 — Première lecture des montants de facture, sans écrire

Mode dry-run : le module analyse les pièces jointes, journalise ce qu'il trouve et
les écarts avec le fichier IMPORT, **sans rien écrire en base**.

Commencer petit, sur un seul mois, pour mesurer le coût et la qualité avant
d'ouvrir en grand :

```powershell
.\.venv311\Scripts\python.exe -m src.scripts.gmail.load_facture --folder data\PJ\202607 --dry-run
```

**Ce qu'il faut relever dans le journal** :

- combien de pièces jointes ont été reconnues comme pièces comptables, et combien
  ont été écartées (un BL ou une packing list doit être écarté, c'est normal et
  souhaitable) ;
- les lignes `[ATTENTION] ... ecart de X %` : ce sont les cas où la facture et le
  fichier IMPORT ne disent pas la même chose. **C'est exactement ce que Marlène
  cherchait le 29/07.** Les recopier telles quelles dans le compte rendu ;
- les lignes `[ATTENTION] ... confiance` : pièces à faire valider à la main ;
- les lignes `[ECHEC]` : documents illisibles.

**Vérifications à faire avec Marlène, sur deux cas qu'elle a cités elle-même** :

| Cas | Attendu |
|---|---|
| Facture HONGXING | montant 6 403,20 et devise **EUR**, pas USD |
| Note de crédit GUANGWEI de cette semaine | reconnue en `note_credit`, montant **négatif** |
| Liasse JIT GLOBAL | montant 19 557,72 retrouvé sur la pièce |

Si ces trois cas ressortent correctement, lancer le chargement réel en retirant
`--dry-run`. Sinon, **ne pas charger** : renvoyer le journal à Antho, le prompt
d'extraction sera ajusté.

---

## Étape 7 — Vérifier l'interface avec Marlène

Redémarrer l'API si elle tourne en processus manuel (c'est le cas sur ce poste),
puis ouvrir l'onglet **Prévisionnel** et contrôler avec elle :

- [ ] Les **numéros de BL** sont revenus dans le tableau des B/L.
- [ ] Les colonnes de montants portent la mention **(IMPORT)** et l'encadré
      d'avertissement est visible au-dessus du tableau.
- [ ] La colonne **Justificatif** affiche BL + facture, BL seul, Facture seule ou
      **Aucun** selon les lignes.
- [ ] Les filtres **Fournisseur** et **Paiement** ouvrent une liste de cases à
      cocher et se cumulent avec la recherche libre.
- [ ] Cocher deux lignes d'un même fournisseur affiche bien un total au-dessus du
      tableau, avec valeur et reste à payer.
- [ ] Cliquer sur la cellule Paiement de la ligne **📦 conteneur** permet de saisir
      une date et de solder tout le conteneur.
- [ ] Cliquer sur la cellule Paiement d'une **ligne fournisseur** fonctionne aussi.

**Deux questions à poser à Marlène, sa réponse est attendue par Antho** :

1. Le 29/07, quand la saisie de la date de paiement a échoué, **quel message exact**
   s'affichait à l'écran ? Une copie d'écran suffit.
2. FUSEAU lui a-t-il **déjà demandé une clé API** sur ce poste, et l'a-t-elle
   saisie ? Si une fenêtre de saisie de clé apparaît maintenant, c'est la réponse.

---

## Étape 8 — Compte rendu à renvoyer à Antho

Un message court, avec les chiffres, pas une description :

```
Runbook 31/07 execute sur le poste de Marlene.

Etape 1 code    : commits presents / absents -> ...
Etape 2 table   : facture_fournisseur, ... colonnes
Etape 3 pip     : pip present / rebootstrappe
Etape 4 cle     : Key Vault / .env / absente
Etape 5 BL      : avant ... conteneurs dont ... avec BL
                  apres ... conteneurs dont ... avec BL
                  blocs sans BL dans le tableau : ... sur ...
Etape 6 pieces  : ... PJ analysees, ... pieces comptables, ... ecartees
                  ecarts > 2 % : <recopier les lignes ATTENTION>
                  HONGXING EUR : ok / ko    GUANGWEI note de credit : ok / ko
                  JIT GLOBAL : ok / ko
                  chargement reel : lance / pas lance et pourquoi
Etape 7 IHM     : cases cochees, et ce qui ne va pas
Marlene         : message d'erreur exact du 29/07 = ...
                  cle API deja demandee sur le poste = oui / non
Etapes STOP rencontrees : ...
```

---

## Ce que ce runbook ne fait pas

- **Il n'affiche pas encore le montant de la facture à côté du montant IMPORT dans
  l'interface.** L'affichage côte à côte avec l'écart attend les règles métier
  demandées à Marlène par mail le 31/07 : ce qui déclenche un paiement, quel
  document fait foi en cas de contradiction, comment s'impute une note de crédit,
  comment se traitent les deposits et DEKRA.
- Il ne traite pas les **deposits, paiements d'avance et DEKRA**, à cadrer en
  séance avec Marlène.
- Il ne planifie pas l'extraction des factures en tâche automatique. On mesure
  d'abord la qualité et le coût sur un mois, on automatise ensuite.
