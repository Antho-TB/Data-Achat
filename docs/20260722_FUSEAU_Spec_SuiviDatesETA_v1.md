# Spec — Suivi des dates ETD/ETA/livraison + alertes de changement

> FUSEAU / Data-Achat · rédigé le 2026-07-22 · **à valider avant tout code**.
> Origine : demande Anthony 22/07 + item backlog `plan_action.md` (« alertes changement ETA →
> Dashboard, mise en forme progressive orange→rouge→violet selon nb de changements »).
> Règle projet : DDL depuis le poste Antho (owner des tables) ; code/commit depuis Windows.

## 1. Objectif

Suivre l'évolution dans le temps des dates de transport (ETD, ETA, date de livraison) par conteneur,
détecter chaque **changement de date**, et le rendre visible :
- **mise en forme conditionnelle** progressive selon le **nombre cumulé de changements** ;
- **remontée d'alerte** vers la carte *Actions prioritaires* du Dashboard à chaque changement d'ETA.

## 2. Décisions actées (22/07)

- **Vérité = dernière date transmise** (pas la première). On **abandonne le COALESCE** actuel de
  `load_ot_gmail` pour ces champs : la valeur la plus récemment transmise gagne, même si elle avance la date.
- **Sources** : fichier maritime transitaire **+ corps des mails** (+ PJ type confirmation d'embarquement).
- **Maille du compteur** : **par conteneur**, historique **cumulé, jamais remis à zéro** (garde la trace
  même après livraison). *(choix c)*
- **Deux indicateurs séparés** : une couleur pour les changements d'**ETA**, une autre pour la **date de
  livraison**. *(choix b)*
- **Échelle couleur** (exemple à confirmer) : 1 changement = 🟠 orange · 2 = 🔴 rouge · 3 et + = 🟣 violet.

## 3. Modèle de données

### 3.1 Nouvelle table `achat.ot_transport_date_evenement` (historique)

| Colonne | Type | Rôle |
|---|---|---|
| `id` | serial PK | |
| `n_conteneur` | text | FK logique → `ot_transport.n_conteneur` |
| `champ` | text | `etd_reel` \| `eta` \| `date_livraison` |
| `ancienne_valeur` | date | valeur courante avant ce changement (NULL si 1re transmission) |
| `nouvelle_valeur` | date | valeur transmise |
| `date_transmission` | timestamp | **horodatage de la transmission** (date du mail, ou date du fichier maritime) |
| `source` | text | `maritime` \| `mail_corps` \| `mail_pj` |
| `source_ref` | text | id message Gmail / nom de fichier (traçabilité + idempotence) |
| `charge_le` | timestamp | date d'insertion technique |

**Idempotence (re-run du pipeline)** : contrainte `UNIQUE (n_conteneur, champ, nouvelle_valeur, date_transmission, source)`.
Un même mail/fichier ré-ingéré ne recrée pas d'événement → pas de double comptage.

### 3.2 `achat.ot_transport` (inchangé en colonnes)

`etd_reel` / `eta` / `date_livraison` = **dernière valeur transmise** (celle du `date_transmission` max).
Le loader ne fait plus COALESCE : il compare la nouvelle valeur à la valeur courante et, si différente,
(a) insère un événement, (b) met à jour `ot_transport`.

### 3.3 Vue `achat.v_ot_transport_suivi` (indicateurs)

Par conteneur : `eta`, `eta_precedente`, `date_livraison`, `nb_changements_eta`, `nb_changements_livraison`,
`couleur_eta`, `couleur_livraison`, `date_dernier_changement_eta`.
- `nb_changements_*` = nombre d'événements où `nouvelle_valeur <> ancienne_valeur` pour ce champ (cumulé).
- `couleur_*` = CASE 1→orange, 2→rouge, ≥3→violet.

## 4. Règle « changement »

En traitant les transmissions **par ordre chronologique** (`date_transmission`) : un changement est compté
quand la valeur transmise **diffère** de la valeur courante. Une re-transmission identique n'incrémente pas.
Tout changement compte (retard **comme** avancement). Jamais de remise à zéro.

## 5. Sources & horodatage

- **Mail (corps + PJ)** : `date_transmission` = date de réception du mail (fiable, par message).
- **Fichier maritime** (gsheet/xlsx transitaire) : c'est un **snapshot** sans date par ligne. Proposition :
  `date_transmission` = date de mise à jour du fichier (ou date d'ingestion ETL). Le changement se détecte en
  comparant le snapshot à la valeur courante en base. **➜ à valider (cf. §7).**

## 6. Dashboard — alerte changement ETA

À chaque nouvel événement `champ='eta'`, alimenter la carte **Actions prioritaires** :
conteneur, PO(s) concernés, `ancienne → nouvelle` ETA, `nb_changements_eta`, couleur.
Tri par gravité (nb de changements décroissant, puis ETA la plus proche).

## 7. Points ouverts à valider (avant code)

1. **Sémantique des 3 dates** : `etd_reel` = départ port ; `eta` = arrivée port ; `date_livraison` =
   arrivée entrepôt TB / réception ? Confirmer, car la couleur porte sur ETA **et** livraison.
2. **Horodatage du fichier maritime** (pas de date par ligne) : date du fichier ou date d'ingestion ? (§5)
3. **Échelle couleur** : 1/2/3+ = orange/rouge/violet — confirmer, et « ≥3 reste violet ».
4. **ETD** : on historise aussi ETD (utile) ou seulement ETA + livraison (les 2 demandés) ?

## 8. Échelons d'implémentation (après validation)

1. **DDL** table `ot_transport_date_evenement` + vue `v_ot_transport_suivi` (migration `sql/`, jouée depuis poste Antho).
2. **Loaders** : `load_ot_gmail` (+ loader maritime) → détection de changement, insertion d'événement, passage en « dernière transmise gagne ». Tests + dry-run.
3. **Ingestion corps de mail** (ETA/livraison) : parsing du corps (skill `achat-gmail-dwh` / `achatanalyser-mail`), alimente les événements. Dépend aussi du chantier `parse_bl extract_table` (PJ, tâche dédiée).
4. **Frontend** : colonnes couleur ETA/livraison (mise en forme conditionnelle) + alerte dans Actions prioritaires.

Chaque échelon : réversible, testé (dry-run), validé, puis commit depuis Windows.
