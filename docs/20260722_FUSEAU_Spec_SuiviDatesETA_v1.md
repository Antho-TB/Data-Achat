# Spec — Suivi des dates ETD/ETA/livraison + alertes de changement

> Mis à jour le 06/10/2026 : modèle de données réaligné sur le code (`achat.transport_evenement` au lieu de `achat.ot_transport_date_evenement`, encadré en §3), points ouverts du §7 marqués tranchés le 23/07, statut passé de « à valider » à « en production ».

> **Statut au 06/10/2026 : implémenté et en production.** Points ouverts tranchés le 23/07 (en-tête de `sql/20260723_suivi_dates_eta_evenements.sql`). Livraison : migration `sql/20260723_suivi_dates_eta_evenements.sql` et commit `8c8df27` (23/07), correctif d'insertion `3a3ba42` (27/07). Lire la §3 avec son encadré d'écarts. Référence à jour du modèle : `docs/modele_semantique.md`.

> FUSEAU / Data-Achat · rédigé le 2026-07-22 · ~~à valider avant tout code~~ validé le 23/07, en production.
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

> **Écarts avec l'implémentation (lecture du code le 06/10/2026).**
> - La table `achat.ot_transport_date_evenement` n'a **pas** été créée. Les événements vont dans
>   `achat.transport_evenement` (créée le 22/07 par `sql/20260722_tables_evenements_metier.sql`) :
>   `type = 'chgt_date'`, `champ_date` ∈ {`eta`, `date_livraison`}, `ancienne_valeur`,
>   `nouvelle_valeur`, `date_info` (date de transmission), `source`. L'idempotence passe par
>   `cle_idempotence` (UNIQUE), construite dans `load_ot_gmail.py` à partir du conteneur, du champ,
>   de la nouvelle valeur, de la date de transmission et du fichier source.
> - `achat.ot_transport` a gagné `eta_maj_le` et `date_livraison_maj_le`, qui mémorisent la date de
>   transmission de la valeur courante. Une transmission plus ancienne est refusée (§4).
> - La vue `achat.v_ot_transport_suivi` existe, sans `eta_precedente` mais avec
>   `date_dernier_changement_livraison`. Elle ne compte que les lignes `type = 'chgt_date'`.
> - L'ETD n'est pas historisé (décision du 23/07, §7).
> - Dans le dépôt, seul `src/scripts/gmail/load_ot_gmail.py` produit des événements `chgt_date`, donc le chemin des
>   pièces jointes Gmail (`deploy/run_gmail_etl.ps1`). Le chargement du fichier maritime par
>   `pipeline.py` passe par `load_ot_transport()` de `src/scripts/etl/load.py`, qui fait un
>   `ON CONFLICT DO UPDATE` sur `ot_transport` sans journaliser le changement ni appliquer la
>   préséance. Constat de lecture du code, non vérifié en base.
> - Les réestimations lues dans le corps des mails arrivent dans la même table avec les types
>   `retard` / `imprevu`, via la tâche Cowork et `load_evenements.py` (types relevés dans l'en-tête
>   de `parse_email_eta.py` ; le prompt Cowork n'est pas versionné, non vérifiable depuis le dépôt).
>   La vue ne compte pas ces types.
>   `parse_email_eta.py` / `load_email_eta.py` existent mais portent depuis le 28/07 la mention
>   « ne pas ordonnancer » (doublon du Cowork, cf. `docs/plan_action.md`).
>
> Le tableau ci-dessous est conservé comme intention d'origine.

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

## 7. Points ouverts à valider (avant code) — tranchés le 23/07

> Réponses (en-tête de `sql/20260723_suivi_dates_eta_evenements.sql`) : 1. sémantique confirmée
> telle quelle ; 2. date du fichier (mtime), appliquée dans `transform_maritime.py` ; 3. 1 = orange,
> 2 = rouge, 3 et plus = violet, jamais remis à zéro ; 4. ETD non historisé.

1. **Sémantique des 3 dates** : `etd_reel` = départ port ; `eta` = arrivée port ; `date_livraison` =
   arrivée entrepôt TB / réception ? Confirmer, car la couleur porte sur ETA **et** livraison.
2. **Horodatage du fichier maritime** (pas de date par ligne) : date du fichier ou date d'ingestion ? (§5)
3. **Échelle couleur** : 1/2/3+ = orange/rouge/violet — confirmer, et « ≥3 reste violet ».
4. **ETD** : on historise aussi ETD (utile) ou seulement ETA + livraison (les 2 demandés) ?

## 8. Échelons d'implémentation (après validation)

> Réalisés, avec les écarts décrits en §3 : la table créée à l'échelon 1 est remplacée par
> `transport_evenement`, et l'échelon 3 (corps de mail) est assuré par la tâche Cowork.

1. **DDL** table `ot_transport_date_evenement` + vue `v_ot_transport_suivi` (migration `sql/`, jouée depuis poste Antho).
2. **Loaders** : `load_ot_gmail` (+ loader maritime) → détection de changement, insertion d'événement, passage en « dernière transmise gagne ». Tests + dry-run.
3. **Ingestion corps de mail** (ETA/livraison) : parsing du corps (skill `achat-gmail-dwh` / `achatanalyser-mail`), alimente les événements. Dépend aussi du chantier `parse_bl extract_table` (PJ, tâche dédiée).
4. **Frontend** : colonnes couleur ETA/livraison (mise en forme conditionnelle) + alerte dans Actions prioritaires.

Chaque échelon : réversible, testé (dry-run), validé, puis commit depuis Windows.
