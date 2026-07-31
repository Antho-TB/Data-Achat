# Plan d'action FUSEAU

> **Source de vérité unique du pilotage projet.** Remplace depuis le 28/07/2026
> les anciens `plan_action.md` (688 lignes), `TASKS.md` et
> `TASKS_POSTE_MARLENE.md`, qui suivaient les mêmes chantiers avec des statuts
> contradictoires. Les trois sont archivés dans `05_ARCHIVES/Versions_Anterieures/`.
>
> **Deadline dure : 31/07/2026**, départ d'Andréa JAMET (Assistante Achats).
> Marlène MONTBRIZON (Responsable Achats) reste et devient l'utilisatrice
> principale.
>
> Documentation technique : `README.md` (installation, architecture),
> `docs/modele_semantique.md` (dictionnaire de données),
> `docs/20260723_FUSEAU_RunbookServiceWindows_v1.md` (exploitation prod).

---

## 1. Où on en est

**L'application est en production** sur le poste de Marlène depuis le 23/07.
Dix onglets opérationnels, 18 endpoints, 22 tables et 7 vues dans le schéma
`achat`. Andréa y accède depuis son poste via le LAN.

Trois automatisations tournent :

| Automatisation | Type | Fréquence | Point de fragilité |
|---|---|---|---|
| `run_api.py` | **Processus manuel** (la tâche `FUSEAU-API` n'a jamais été installée sur ce poste, constat du 28/07) | Lancement à la main | Ne redémarre pas seule après reboot ou fermeture de session |
| `FUSEAU_Gmail_ETL` | Tâche planifiée Windows | Toutes les 2 h, 08h-18h | Idem, mais ne dépend pas de Cowork |
| `fuseau-gmail-threads-achat` | Tâche Cowork (extraction LLM) | Non fixée | S'arrête si l'app Claude est fermée |

**Le risque numéro un du projet n'est pas fonctionnel, il est structurel** :
tout tourne sur la session Windows d'une personne. C'est l'objet du chantier 3.

---

## 2. Priorité 1 — avant le 31/07 (départ d'Andréa)

Ce qui n'existe que dans sa tête et disparaît avec elle. **Trois jours restants.**

### 2.1 Questions métier tranchées (28/07)

Toutes les questions ouvertes du plan de charge ont été clarifiées avec le métier :

| # | Question | Décision / Réponse métier (28/07) | Statut |
|---|---|---|---|
| Q-A | Codes couleurs pour les statuts | **Ignorer les couleurs historiques d'Andréa** : priorité stricte au **Design System TB Groupe**. | ✅ Tranché |
| Q-B | `etd_confirme` & groupage conteneur | ETD confirmé = date ferme. Le KPI retard se base sur cet écart. | ✅ Tranché |
| Q-C | Champ « prioritaire » sur Promo/Opé | Choix métier direct : les règles de remplissage sont connues au sein du service Achats. | ✅ Tranché |
| Q-D | Source de la **packing list** | **Envoyée par TB China (Julia) par mail.** Ce n'est **pas** un élément de la Fiche Achat et elle n'est pas produite par Andréa. Corrige la réponse notée plus tôt le 28/07. | ✅ Tranché |
| Q-E | Statut commande reçue en quarantaine | **Rester active / en attente** : statut connu par le WMS Bext mais non géré par l'ERP Sylob. | ✅ Tranché |
| Q-F | Notion de PO **critique** | Déterminé par le caractère **conteneur bloquant**. | ✅ Tranché |
| Q-G | Variantes template Fiche Achat | Modèles Produit unique vs Ménagère/Sets intégrés dans le générateur Fiche Achat. | ✅ Tranché |

### 2.2 Savoir non transmissible résolu (28/07)

Les deux cases qui restaient vrac/inconnues dans la carte mentale d'Andréa ont leurs propriétaires identifiés :
- **Plan de production** : Géré directement par le **Bureau d'Études (BE)** de l'entreprise, au sein de l'entité **GDD**.
- **Image d'emballage** : Gérée par **Clarisse (service Design)**, ou prise de vue directe photo par Andréa pour alimenter la Fiche Achat.

### 2.3 Actions

- [x] **Séance de captation métier (28/07)** : Validation des 7 questions Q-A à Q-F + gouvernance plan de prod et images emballage.
- [x] Identifier les responsables BE/GDD et Design pour les plans et images d'emballage.
- [ ] Vérifier que **Maxence** (repreneur de la boîte mail) est bien câblé sur les fils fournisseurs, et que Marlène reste en copie systématique.

---

## 3. Priorité 2 — pérennisation de l'infrastructure

Sortir du bus factor « poste de Marlène ». Chantier porté avec **Samuel** (IT
Réseau / Nubo).

### 3.1 Windows Server dédié

Procédure complète rédigée le 27/07 :
`docs/20260727_FUSEAU_Procedure_Deploiement_WindowsServer_v1.md`. Cible
`D:\Apps\FUSEAU`, trois utilisateurs (Marlène, Andréa, Maxence). **Rien n'est
encore déployé**, Samuel prépare la machine.

- [ ] Valider les 7 prérequis serveur avec Samuel
- [ ] Cloner le dépôt, créer le venv 3.11, recopier **manuellement** les 3 secrets (`.env`, `credentials.json`, `token.json`) — jamais par Git ni par mail en clair
- [ ] Installer le service (NSSM recommandé) + règle firewall entrante 5050 sur le LAN
- [ ] Rapatrier la tâche `FUSEAU_Gmail_ETL` + les binaires OCR (Tesseract, Poppler)
- [ ] Basculer les utilisateurs, **puis arrêter l'instance du poste de Marlène** (deux instances concurrentes en écriture = corruption garantie)

✅ **Incohérence levée (28/07)** : l'adresse obsolète `192.168.102.21:5433` a été éliminée de la procédure de déploiement et du code (`config_manager.py`). La cible unique retenue est le DWH Sylob V25 `SRV-ERP-DATA 192.168.102.41:5432`.

### 3.1 bis Accès d'Andréa en attendant le serveur

Solution provisoire retenue le 28/07 : **aucune installation sur son poste.**
FUSEAU est une application web, Andréa l'ouvre dans son navigateur sur l'adresse
réseau du poste de Marlène. Copier le dépôt sur son poste a été explicitement
écarté : deux instances écrivant dans la même base de production, c'est la
corruption de données assurée.

Procédure exécutable, écrite pour l'assistant du poste de Marlène :
`docs/20260728_FUSEAU_AccesLAN_Andrea_Runbook.md`.

- [x] `API_HOST=0.0.0.0` dans le `config/.env` du poste de Marlène — fait le 28/07, l'API écoute bien en `0.0.0.0:5050`
- [ ] **Règle de pare-feu entrante port 5050, profils Domain et Private — BLOQUANT.** Échec le 28/07 : « Accès refusé », console non administrateur. Tant qu'elle n'existe pas, Andréa ne peut pas se connecter.
- [ ] Transmettre l'URL à Andréa (`http://192.168.104.144:5050`, IP Wi-Fi susceptible de changer) et lui communiquer la clé API de vive voix
- [ ] Décider : installer la tâche planifiée `FUSEAU-API` pour la persistance, ou assumer le lancement manuel jusqu'au serveur de Samuel

⚠️ **L'IP du poste de Marlène est en Wi-Fi et peut changer** au prochain bail
DHCP, ce qui casserait le favori d'Andréa. Réservation DHCP à demander, ou
attendre le serveur.

### 3.2 Comptes de service et ownership

- [x] **Compte AD `svc-dataachat`** — Compte existant et mot de passe versé dans Key Vault (`kv-dtpf-prod` -> `svc-dataachat-ad-password`). **Permet à l'ETL d'accéder directement en lecture aux fichiers Excel sources sur le serveur de fichier** (`\\Srv-files-pom\partage\ADA\METIER\SUIVI CDES IMPORT\`) sans repasser par des copies locales sur le poste d'Antho/Marlène, et à faire tourner le service Windows.
- [ ] **Login PostgreSQL `dtpf_sylob_dataachat_prod`** (modèle : `dtpf_sylob_myreport_prod`), membre de `platform_team`.
- [ ] **REASSIGN de l'ownership** des objets `achat.*` du login personnel `dtpf_sylob_anthony_bezille_prod` vers `platform_team`. Exige l'identité admin Entra / `azure_pg_admin`.

Tant que ces trois points ne sont pas faits, **le projet dépend d'un compte
nominatif**, ce qui est précisément le problème qu'on cherche à éliminer.

### 3.3 Environnement de test

- [ ] Base `dtpf_sylob_test` + `config/.env.test` + garde-fou anti-prod. Jamais démarré. Aujourd'hui, tout write de test se fait directement en production — c'est ce qui s'est passé le 22/07 pour le premier chargement `ot_transport`.

---

## 3.4 Couverture réelle des sources — audit du 28/07

Question posée par Antho : « est-ce qu'on capte bien toutes les sources, et
est-ce automatique ? » Réponse vérifiée module par module (quel script est
appelé par quel pipeline ou quelle tâche planifiée) et recoupée avec la
fraîcheur réelle des tables. **Deux chaînes sur huit sont automatisées.**

### Automatisé

| Chaîne | Déclencheur | Alimente | Fraîcheur constatée |
|---|---|---|---|
| **Fichiers du partage réseau** (IMPORT 2026, Matrice, dimensions, SUIVI MARITIME) → `pipeline.py` puis étape ENRICH | `run_etl_scheduled.ps1` ⚠️ **vérifier que la tâche est bien installée sur le poste de Marlène** | `commande`, `produit`, `qualite`, `acompte`, `ot_transport`, `artwork` | 28/07 |
| **Pièces jointes Gmail (BL)** : `preflight_gmail` → `fetch_attachments` → `parse_bl` → `load_ot_gmail` | Tâche `FUSEAU_Gmail_ETL`, toutes les 2 h, 8h-18h, poste de Marlène | `ot_transport` (n° BL) | 28/07 |

| **Décisions métier depuis le corps des mails** : tâche Cowork → `load_evenements` | Tâche Cowork, toutes les 2 h, poste de Marlène | `qualite_decision`, `transport_evenement`, `commerce_decision`, `design_evenement` | 28/07 |

**Correction du 28/07 au soir.** J'avais d'abord conclu que l'email-first ne
tournait pas. C'est faux : la tâche Cowork fonctionne et produit. Vérifié en
base — 45 décisions qualité entre le 22 et le 28/07, dont 38 conformes et 7 non
conformes ventilées par stade (BAT, SP, réception, MAT), plus les retards et
imprévus transport avec leurs nouvelles ETA et ETD. La table a d'ailleurs gagné
des lignes entre deux requêtes espacées de quelques minutes. Ce qui n'a jamais
tourné, ce sont les **modules Python** qui font le même travail en double.

### Non automatisé

| Source | Modules concernés | Conséquence mesurée | Décision |
|---|---|---|---|
| **Rapports qualité du Drive** | `crawl_drive_qualite`, `load_qualite_doc_drive` | `qualite_doc` et `qualite_analyse` : 8 lignes chacune, **figées au 02/07** | ✅ **À planifier 1×/jour** |
| **Gsheet Artwork (Clarisse)** | `transform_artwork`, `load_artwork` | `artwork_statut` figé au **22/07** | ✅ **À planifier 1×/jour** |
| **Enrichissements Sylob on-premise** : CA fournisseur 3 ans, référentiel article (prix, délai), dimensions et packaging | `enrich_ca`, `enrich_from_sylob`, `enrich_dimensions` | Ne tournaient pas sur le poste de Marlène | ✅ **À planifier** — voir ci-dessous |
| MIF, STOP REF, lots multiples, nomenclature | `transform_mif`, `transform_stop_ref`, `transform_lot_multiples`, `transform_nomenclature` | Copies one-shot de mars | ⛔ Reprise manuelle assumée |
| Acomptes depuis Sylob | `enrich_acompte` | Superseded | ⛔ **Obsolète** : `load_acompte` charge depuis la colonne Acompte de l'IMPORT, qui est la source métier officielle (le montant est absent côté ERP) |

### Enrichissements Sylob : ils fonctionnent, il leur manquait les identifiants

Correction du 28/07 au soir. Ces trois modules avaient été écartés du poste de
Marlène parce qu'« ils ne marchaient pas ». **Le code n'est pas en cause** : le
poste de Marlène n'a tout simplement pas les identifiants du DWH Sylob
on-premise (`SYLOB_*` absents de son `config/.env`), et `get_sylob_url()` lève
alors une erreur. Ce sont pourtant des informations dont le métier a besoin,
dont le CA fournisseur sur 3 ans glissants, demandé dans trois comptes rendus
de démo.

Vérifié et exécuté depuis le poste d'Antho, qui a les identifiants :

| Module | Résultat réel |
|---|---|
| `enrich_dimensions` | 1188 articles sur 1199 enrichis en dimensions et packaging depuis Sylob V25 |
| `enrich_from_sylob` | 1195 articles enrichis (prix du dernier achat, délai de réappro) |
| `enrich_ca` | 21 fournisseurs, 12,8 M$ de CA sur 3 ans glissants |

- [ ] **Renseigner les identifiants Sylob dans le `config/.env` du poste de Marlène** : `SYLOB_HOST=192.168.102.41`, `SYLOB_PORT=5432`, `SYLOB_DB=tarrerias_production_dwh`, `SYLOB_USER=dataviz-admin`, `SYLOB_PASSWORD` à saisir localement, jamais transmis par écrit
- [ ] **Ajouter les trois modules à la tâche quotidienne** `run_daily_etl.ps1` une fois les identifiants en place
- [ ] Cible serveur : étendre `get_sylob_url()` au Key Vault, comme `get_pg_url()`, pour sortir ce mot de passe des `.env` en clair

### Doublon d'implémentation tranché

`parse_email_ncr` / `load_email_ncr` et `parse_email_eta` / `load_email_eta`
sont une **seconde implémentation, à base de regex, de ce que la tâche Cowork
fait déjà**. Ils n'ont jamais tourné.

**Décision du 28/07 : le Cowork reste la référence.** Un LLM lit une formulation
libre d'Eric T ou d'un transitaire bien mieux qu'une expression régulière, et il
est en production avec de la donnée réelle. Les modules Python sont conservés
comme repli documenté — le jour où l'on voudra sortir de la dépendance à
l'application Claude ouverte — mais portent désormais un avertissement en tête :
**ne pas les ordonnancer**. Les lancer en parallèle du Cowork créerait des
doublons dans deux tables différentes.

Fragilité assumée en contrepartie : **la captation s'arrête si l'application
Claude est fermée sur le poste de Marlène.** À surveiller, et à reconsidérer au
passage sur le serveur de Samuel, où le repli Python reprendra du sens.

### Actions

- [ ] Vérifier que la tâche ETL fichiers est installée sur le poste de Marlène (la tâche Gmail l'est, l'API ne l'est pas : ne rien supposer)
- [ ] **Installer `FUSEAU_Daily_ETL`** (`deploy/run_daily_etl.ps1`, 07h00) : artwork gsheet + Drive qualité
- [ ] **Avant l'installation : consentement OAuth à refaire une fois à la main.** Le scope `spreadsheets.readonly` a été ajouté après la création du `token.json` existant ; Google ne le signale qu'à la première requête Sheets. Supprimer `config\token.json`, lancer le script manuellement, valider dans le navigateur. Impossible depuis une tâche planifiée.
- [ ] Vérifier que le classeur `LIS-CON-28-0` est bien partagé avec le compte Google utilisé par FUSEAU

---

## 3.5 Retours de la démo du 28/07 (notes d'Antho)

Notes brutes de la séance, à trier avec Marlène. Andréa doit envoyer les siennes.

**Données et captation**

- **Factures parfois en JPEG**, packing lists parfois en Excel. Le parseur de pièces jointes doit couvrir ces formats, pas seulement le PDF. À croiser avec la captation packing list (§5.2).
- **BL SZSE2608065 absent.** Vérifié le 28/07 : il n'est **ni dans la base, ni dans le fichier serveur `2026 SUIVI MARITIME.xlsx`** (pourtant modifié le jour même à 11h11). Il ne peut donc venir que de la pièce jointe Gmail. Piste : la chaîne PJ n'a pas tourné, ou n'a pas su parser ce BL. À diagnostiquer sur le poste de Marlène, seul endroit où elle s'exécute.
- **Conteneur TEMU7385996 incorrect.** Même constat : absent de la base et du fichier transitaire. Même piste.
- ⚠️ **Hypothèse à lever** : Antho note « PJ réceptionnée et Gsheet à jour ». Si le transitaire tient à jour le **gsheet** pendant que l'ETL lit le **fichier serveur**, on lit une copie. Vérifier laquelle des deux sources fait foi aujourd'hui.
- **Avoirs fournisseurs absents du prévisionnel.** Aucune table ne les porte. Source et règle de gestion à définir.

**Fonctionnel**

- **Champ « Prioritaire » Oui/Non** dans le suivi des commandes, pour filtrer dans le suivi des OP. Rejoint la demande de flag promo modifiable (§5.2) et la question Q-C.
- **Faire valider les documents de sortie par le service Qualité** (Fiche Achat exportée, rapports).
- **Export PDF à revoir : il imprime toute l'application** au lieu de la seule fiche. Bug de périmètre `@media print`.

---

## 3.6 Suite des retours d'Andréa — arbitré le 28/07 au soir

### Livré

- [x] **Format de date JJ/MM/AA** dans toute l'application. L'ISO reste la valeur stockée et triée, on ne formate qu'à l'affichage.
- [x] **Date de livraison estimée = ETA + 7 jours** sur l'onglet Conteneurs, affichée en gris tant que le transitaire n'a pas confirmé, effacée dès que la date ferme est connue.
- [x] **Filtre par année** sur le suivi de commande, année en cours présélectionnée, années antérieures accessibles d'un clic. 467 lignes affichées sur 802.
- [x] **Priorité d'affichage** : les lignes en retard remontent en tête quel que soit leur statut, puis en production, en cours de livraison, livré, payé, annulé. À rang égal, l'échéance la plus proche d'abord.
- [x] **Discrimination BL / conteneur** (ISO 6346) et purge des 27 lignes fautives.

### Bascule sur le gsheet maritime — codée, reste à activer

Classeur confirmé par Antho le 28/07 : « SUIVI MARITIME TARRERIAS 2026 » est bien
le gsheet `1hP73oivXrB8o8I7pkrGh7y6nPzn0ccfW` déjà documenté. Sa structure à 18
colonnes correspond exactement aux lettres citées par Andréa — conteneur en J,
BL en M, date confirmée en P, heure en Q.

- [x] **Lecture directe du gsheet** dans `extract_suivi_maritime`, avec repli automatique sur le fichier serveur si Google est injoignable
- [x] **Date et heure de livraison confirmées** assemblées en horodatage (`date_livraison` est déjà un timestamp). Gère `08:00`, `14h30`, `8h`
- [x] **Plusieurs BL par conteneur** : table `achat.ot_transport_bl` (grain conteneur + BL), 29 BL repris de l'existant. `ot_transport.n_bl` conserve le BL principal pour ne pas casser les vues. L'API agrège et le front affiche un compteur quand il y en a plusieurs
- [ ] **Activer sur le poste de Marlène** : mettre `SUIVI_MARITIME_PATH=gsheet` dans `config/.env` et renseigner `SUIVI_MARITIME_PATH_FICHIER` avec le chemin serveur comme repli. Le défaut du code est déjà `gsheet`, mais le `.env` existant surcharge avec le chemin fichier
- [ ] **Prérequis OAuth commun avec l'artwork** : le scope `spreadsheets.readonly` exige un reconsentement manuel une fois (cf. §3.4)
- [ ] Vérifier que le classeur est partagé avec le compte Google de FUSEAU
- [ ] Après la première exécution : contrôler que les BL manquants signalés en démo (`SZSE2608065`, `TEMU7385996`) remontent bien

### À faire lors de la prochaine session sur le poste de Marlène

- [ ] **Capter le mail DEKRA de réservation d'inspection.** Il arrive 2 à 7 jours avant l'inspection et n'est aujourd'hui capté nulle part. Il débloque trois demandes d'un coup : le statut « Inspection en cours » avec sa date réservée sur le suivi de commande, le statut « En attente de livraison » (rapport confirmé, BL pas encore reçu), et l'affichage de la date d'inspection réservée sur l'onglet Qualité, qui n'affiche aujourd'hui que les inspections passées ou du jour. C'est la tâche Cowork qui doit le lire, pas une expression régulière : le mail est en langage libre.

### Autres retours en attente

- [ ] **Alerte prioritaire pour sélectionner les références** sur le suivi de commande (même sujet que le champ « Prioritaire », §3.5).

---

## 3.7 Retours de Marlène du 29/07 — session de paiement réelle

Mail « 260729 FUSEAU – TEST ONGLET PRÉVISIONNEL – PAIEMENTS ». Premier usage de
l'onglet Prévisionnel en conditions de paiement (elle règle les fournisseurs le
matin, tableau import et pochette de paiement à côté). Deux natures de retours
à ne pas mélanger : un **défaut de provenance des montants**, et de
l'**ergonomie de sélection**.

### Défaut de provenance — le sujet grave

Le tableau « B/L en attente ou bloqués » affichait un badge de source
« Suivi Maritime + Gmail BL » pour l'ensemble de la section, montants compris.
C'est faux : `valeur` et `valeur_a_payer` sortent **exclusivement** de
`achat.commande` (IMPORT 2026.xlsx + Sylob). Le maritime et Gmail n'alimentent
que le BL, l'ETD/ETA et le n° de facture — **aucun montant n'est extrait des
pièces jointes à ce jour** (`parse_bl.py` capte `n_facture`, jamais de montant).

Conséquence relevée par Marlène : sur HONGXING, FUSEAU affichait un montant issu
du fichier IMPORT alors que la facture reçue par mail porte **6 403,20 EUR** ;
une autre ligne affichait un montant sans BL, sans facture et sans trace
maritime. Son verdict : « très dangereux, nous ne sommes plus censés
l'utiliser à terme ». Elle a raison — l'interface présentait comme corroborée
une donnée qui ne l'était pas.

- [x] **Provenance rétablie dans l'interface (31/07)** : badge de section scindé
      (« BL / dates : Maritime + Gmail » vs « Montants : IMPORT 2026.xlsx »),
      en-têtes des colonnes de montants marquées `(IMPORT)`, avertissement
      explicite au-dessus du tableau, et nouvelle colonne **Justificatif** qui
      qualifie chaque ligne (BL + facture / BL seul / Facture seule / **Aucun ⚠**).
      `n_facture` est désormais exposé par `/api/previsionnel`.
- [ ] **Extraire le montant de facture des PJ Gmail** — chantier structurel, non
      couvert. Cible : montant + devise + n° de facture stockés hors
      `achat.commande` (full-refresh), donc dans
      `achat.commande_enrichissement` (colonnes à ajouter) ou une table
      `achat.facture_fournisseur` dédiée si le grain est la facture et non le PO.
      L'interface devra afficher **montant IMPORT et montant facture côte à
      côte** avec un écart signalé, jamais un seul chiffre de provenance floue.
      Décision de grain à trancher avant de coder.
- [ ] **Devise** : Marlène cite un montant en EUR, les colonnes FUSEAU sont en
      USD. Le montant de facture devra porter sa devise, sans conversion
      implicite.
- [ ] **Credit note GUANGWEI** reçue par mail cette semaine : absente. Même
      chantier — une note de crédit est un montant négatif de liasse.
- [ ] **JIT GLOBAL à 0** alors que la liasse mail porte 19 557,72 : à qualifier
      (aucune ligne rattachée dans l'IMPORT, ou lignes considérées soldées).

### Ergonomie de la session de paiement

- [x] **Filtre multi-valeurs façon Excel (31/07)** : cases à cocher par
      fournisseur et par statut de paiement (« ajouter au filtre »), cumulables
      avec la recherche libre.
- [x] **Sélection de lignes totalisée (31/07)** : case à cocher par ligne et par
      conteneur, barre de totaux (valeur + reste à payer) au-dessus du tableau,
      calculée sur la sélection quand il y en a une, sinon sur le filtre. Répond
      au cas « je ne paie que 2 factures HONGXING sur 5 » sans repasser par la
      calculette.
- [x] **Colonne « Reste à payer · USD »** exposée dans le tableau : elle
      existait côté API (`valeur_a_payer`) et n'était pas affichée.

### Bugs restants signalés le 29/07 — non traités

- [ ] **Les n° de BL ne remontent plus** dans ce tableau, alors qu'ils
      s'affichaient la veille. Marlène croise systématiquement n° de conteneur
      et n° de BL. Piste : bascule sur le gsheet maritime / `ot_transport_bl`
      (§3.6) — le BL principal de `ot_transport` a pu se vider.
- [ ] **Saisie de la date de paiement impossible**, y compris sur les liasses
      sans anomalie (capture d'écran fournie). À reproduire : clé API,
      `conteneurSansLigne`, ou refus de l'endpoint
      `PUT /api/paiement/conteneur/{n}`.
- [ ] **Deposits / paiements d'avance / DEKRA** : à cadrer à la prochaine
      session de travail avec elle.

---

## 4. Priorité 3 — dette et incohérences à arbitrer

### 4.1 Bloqué par une action externe

| Sujet | Blocage | Qui peut lever |
|---|---|---|
| **Statut « Livrée » depuis Sylob** | Aucune table accessible ne porte une date de réception réelle jointe à PO + article. `bi_reporting.fact_achats_consolides` est la seule à en avoir une, mais accès refusé au login applicatif et grain inexploitable. | IT / owner de la base. Résolu partiellement le 28/07 par `public.receptions_detaillees2` (voir §5), reste le grain article. |
| **Code article dans les rapports d'inspection Qualité** | Les PDF ne portent pas le code article, seul le PO permet de les raccrocher : un rapport ne peut donc pas être rattaché à une ligne précise d'une commande multi-articles. Proposition métier : que le service Qualité le mette dans le nom du fichier. | Service Qualité (décision de process, pas de dev) |
| **Raison du retard** | **Source retenue (28/07) : parsing du corps de mail transitaire** via `parse_email_eta.py` (extraction regex du motif/incident vers `transport_evenement`). | ✅ Métier (tranché) |

### 4.2 Documents désalignés du code

- [ ] **`docs/20260722_FUSEAU_Spec_SuiviDatesETA_v1.md`** prévoit une table `achat.ot_transport_date_evenement`. L'implémentation réutilise `achat.transport_evenement`. La spec n'a jamais été mise à jour et affiche encore « à valider avant tout code » alors que le code est en production.
- [ ] **`docs/20260722_FUSEAU_Cartographie_FluxGmail_v1.md`** marque « Non capté » les changements d'ETA, implémentés depuis (`parse_email_eta.py`, `load_email_eta.py`).
- [ ] **`docs/20260723_FUSEAU_Passation_MiseEnProd_PosteMarlene_v1.md`** §5 décrit un blocage `transport_evenement` résolu le 27/07, et §2 s'interroge sur git vs robocopy — tranché de fait, le poste utilise git.
- [ ] **`docs/20260722_FUSEAU_Runbook_TablesEvenements_ClaudePosteAntho.md`** décrit une procédure DDL déjà exécutée, depuis le poste de Marlène et non celui d'Antho.

### 4.3 Chiffres à fiabiliser

- [ ] **Retard WANXIN** : trois valeurs dans trois documents (102 j, 182 j, 444 j). Le chiffre a été vérifié le 23/07 et n'est pas une saisie erronée, mais l'écart entre les trois sources n'a jamais été expliqué. Ne pas citer ce chiffre en réunion tant que ce n'est pas clair.
- [ ] **Fraîcheur des sources figées** : `Matrice Lot Multiples`, `POINT MIF` et `STOP REF CARREFOUR` ont été ingérés depuis des copies datant de mars. À rafraîchir.
- [ ] **Mapping des 47 colonnes de l'IMPORT** : plusieurs colonnes restent non vérifiées (`OP/Client/Appro`, `Alerte`, `Nombre de mois`, `Prix / référence`, `Total prix sur facture`, `MAT / SP / Échantillon de conformité`).

---

## 5. Backlog fonctionnel

Priorisé par récurrence dans les comptes rendus de démo : une demande qui
revient dans trois documents est une vraie priorité, une demande citée une fois
peut attendre.

### 5.1 Demandé dans 3 documents ou plus

| Demande | Statut |
|---|---|
| Aucun chiffre affiché sans unité ni définition (règle transverse, pas un ticket) | Largement fait, à maintenir sur tout nouvel écran |
| Carte « Actions prioritaires » cliquable et triée | Fait |
| Séparer les axes paiement / logistique / qualité | Fait |
| Prévisionnel financier + horizon 2-3 mois pour l'achat de dollar | Fait |
| Fiche Achat : consultation, mise à jour, génération PDF et xlsx | Fait (Phase B livrée le 27/07) |
| Retard = ETD réel − ETD confirmé, 12 mois glissants, figé | Fait |
| Onglet Conteneurs, le conteneur comme unité d'expédition et de paiement | Fait |
| CA fournisseur borné à 3 ans glissants | Fait |
| **Détection de non-conformité via le mail de rejet d'Eric T** | **Codé le 28/07, jamais exécuté sur des mails réels** |
| Cohérence des libellés entre onglets | Fait |
| Ingestion Matrice TB Import comme référentiel nomenclature | Fait |

### 5.2 Reste à faire

- [ ] **Artwork : écriture depuis FUSEAU.** Demandé le 21/07 (« simulateur de gsheet »). ⚠️ **Contradiction à arbitrer avant de coder** : le modèle actuel est insert-only et pose que le statut appartient à Clarisse, que l'ETL n'écrase jamais. Autoriser l'écriture depuis FUSEAU crée un conflit d'autorité sur la donnée. Trancher avec Clarisse.
- [ ] **Artwork : coller aux colonnes exactes du gsheet `LIS-CON-28-0`** et à ses formats de date.
- [ ] **Étendre la détection qualité aux mails de validation.** `parse_email_ncr.py` ne reconnaît que les rejets. Règle corrigée le 28/07 : la conformité est elle aussi validée par mail (voir §6), les deux décisions sont donc captables.
- [ ] **Capter la packing list depuis les mails de TB China.** Tranché le 28/07 : elle vient de Julia par mail, pas de la Fiche Achat. C'est la troisième pièce de la liasse de paiement (BL + facture + packing list), les deux premières étant déjà suivies. Même mécanisme que le BL (`fetch_attachments` puis un parseur dédié), et une colonne à ajouter côté `achat.*` : aucune ne la porte aujourd'hui.
- [ ] **Flag promo modifiable** à plusieurs étapes du circuit (aujourd'hui figé à la création).
- [ ] **HITL** : point de validation humaine quand deux sources se contredisent (date d'un mail contre Sylob, prix négocié qui bouge).
- [ ] **Extractions régulières** (gsheet, Excel, PDF) au lieu d'exports manuels ponctuels.
- [ ] **Passe de vérification systématique** de cohérence Sylob vs `achat.*` (article, fournisseur, EAN).
- [ ] **Alertes imprévu majeur** (grève, incident logistique). ⚠️ Aucune source de données identifiée : alerte manuelle, flux transitaire, ou API tierce ? À qualifier avant tout dev.
- [ ] **Chemin critique** sur le suivi de commande — dépend de Q-F.
- [ ] Aging des artworks + relance de Clarisse au-delà de X jours (seuil à fixer).
- [ ] Passage à l'échelle du pilote Drive qualité (~48 PO).

### 5.3 Écarté volontairement

- **Historique de prix approfondi** : la donnée est déjà dans Sylob. Décision du 07/07 de ne pas réinvestir et de former l'équipe sur Sylob natif. Ce qui existe dans FUSEAU suffit à la transition.
- **Onglet Article élargi au stock et au cycle de vie** : périmètre Supply Chain, hors Achats.
- **GDD** : circuit qualité distinct de TB, moins formalisé. Priorité basse, ne pas généraliser la logique TB.
- **Fiches achat PDF du Drive (source 6)** : basse priorité.
- **Docker** : reporté au passage sur serveur, non repris dans la procédure du 27/07.
- **n8n (Plan B pour les PJ Gmail)** : workflow `j2HdoDnRAFgG81w2` monté mais jamais activé. Le Plan A fonctionne en production, on garde n8n en réserve sans l'entretenir.

---

## 6. Règles métier de référence

Ce qui ne doit pas se reperdre. Détail complet dans `docs/modele_semantique.md`
et le questionnaire de sourcing du 27/07.

**Délais.** Retard d'expédition = `ETD réel − ETD confirmé`, moyenne par
fournisseur sur 12 mois glissants, **figée à l'ETD** (jamais recalculée contre
la date du jour), avances plancheées à 0, garde-fou à 180 jours. Ce n'est pas
`date_livraison − ETD`. ETD standard = commande + 90 jours sauf urgence. Délai
ETD → ETA ≈ 60 jours.

**Paiement.** Déclenché par le BL. Liasse complète = BL + facture + packing
list. **La packing list est envoyée par TB China (Julia) par mail** : elle ne
fait pas partie de la Fiche Achat et n'est pas produite en interne. C'est donc
une pièce jointe de mail, au même titre que le BL, et elle relève du même
mécanisme de captation. Aucune colonne du schéma `achat.*` ne la porte à ce
jour. Retard de paiement au-delà de `ETD_BL + 15 jours`. Tous les montants sont
en **USD**, quelle que soit la source. Le conteneur est l'unité réelle
d'expédition et de paiement. Montants calculés en `PU × quantité`, jamais via
`total_prix`.

**Livraison vs paiement.** **Sylob est la source de vérité de la livraison** ;
le rapprochement des réceptions physiques bascule automatiquement le statut en
« Livrée ». Le **paiement** relève du process Achats et se saisit dans FUSEAU.

**Qualité.** La conformité **comme** la non-conformité sont validées par mail :
les deux décisions laissent une trace écrite, Eric T (Commerce) étant le
décideur. Un mail existe donc dans les deux sens, ce qui rend la détection
symétrique possible.

> ⚠️ **Correction du 28/07 qui annule la règle du 07/07.** Le questionnaire de
> démo (Q1-2) avait acté « conforme = validé par défaut, pas de mail formel »,
> d'où une détection volontairement asymétrique : on ne captait qu'un rejet,
> jamais une validation. C'est faux. Conséquence à traiter :
> `src/scripts/gmail/parse_email_ncr.py` ne reconnaît aujourd'hui que les mails
> de rejet (mots-clés `KEYWORDS_REJET`) et ignore les validations. Il faut
> l'étendre pour capter les deux décisions.

**En attente : identifier les rapports par code article.** C'est le point
bloquant du rapprochement qualité, déjà listé au §4.1 : les PDF d'inspection ne
portent pas le code article, seul le PO permet de les raccrocher. Tant que ce
n'est pas résolu, un rapport ne peut pas être rattaché à une ligne article
précise d'une commande multi-articles.

Dureté HRC mesurée uniquement sur les couteaux : un NULL est une absence de test
légitime. Chrome : 13 % sur les produits coupants, 16-18 % sur les autres
couverts. Stades : `MAT`, `SP`, `BAT`, `RECEP`.

**Codes et identifiants.** Code article créé par Emmanuelle **dès la commande
fournisseur**, prérequis = la gamme ; avant, c'est un prototype avec un code
provisoire. N° de lot au format `AAMMJJHHMM`. EAN : Item = EAN13, Inner = EAN14
SPCB, Master = EAN14 PCB. Un seul transitaire (QUALITAIRSEA), port de
destination constant (FOS SUR MER).

**Alias fournisseurs.** POLLYDA + DIAMOND TRACK = GUANGWEI · HUGUESUN + SMART
IRON = JIT GLOBAL · HIAMEA = AOYAM · VICO = MINGHAO. Regroupement par `frn_code`
(identifiant Sylob), jamais par le nom.

**Échantillons.** Existant en vrac : Raw material, Semi-production, Production.
Existant + packaging spécial : + Printing sample. Nouveau en vrac : + Compliance
sample. Nouveau + packaging spécial : les 5. Port toujours payé par TB.

**Sources de vérité. Règle générale, posée le 28/07 :** dès qu'un document est
**tenu de façon collaborative avec un tiers**, c'est le **gsheet** qui fait foi,
pas la copie serveur. C'est là que le travail se fait vraiment. Deux cas
aujourd'hui : le suivi maritime, tenu avec le transitaire, et le suivi des
artworks, tenu avec Clarisse. Dans les deux cas **lecture seule** : FUSEAU ne
modifie jamais un document partagé.

> ⚠️ **Ceci renverse la décision du 30/06** qui posait « serveur = source de
> vérité, gsheet = POC » pour le maritime. Conséquence mesurée : l'ETL lit
> depuis le 28/07 un fichier serveur de 14 colonnes **sans colonne BL**, alors
> qu'Andréa et le transitaire travaillent sur un gsheet qui en a au moins 17
> (conteneur en J, BL en M, date de livraison confirmée en P, heure en Q).
> C'est ce qui explique les BL introuvables signalés en démo.

EAN et PCB → Sylob. Marquage, matière, packaging détaillé → fiche achat
existante. Fiche achat → serveur `\\Srv-files-pom\...`. Qualité → serveur
`ANALYSES ET INSPECTIONS` (le Drive est un POC).

**Un conteneur peut porter plusieurs BL** : ils sont édités par les
fournisseurs, et un conteneur groupe plusieurs fournisseurs. Le modèle actuel ne
le permet pas, `achat.ot_transport` ayant le conteneur pour clé primaire et une
seule colonne `n_bl`.

**Un numéro de BL n'est pas un numéro de conteneur**, même s'ils se ressemblent.
La norme ISO 6346 impose que la 4e lettre d'un conteneur soit U, J ou Z :
`TEMU2613140` est un conteneur, `SZSE2604053` est un BL. Sans ce discriminant,
27 BL avaient été enregistrés comme conteneurs (corrigé le 28/07).

**Architecture, règle absolue.** `achat.commande` et `achat.qualite` sont
rechargées en full-refresh (TRUNCATE + INSERT). **Aucun module d'enrichissement
ne doit y écrire directement.** Les saisies utilisateur passent par
`achat.commande_annotation`, les enrichissements automatiques par
`achat.commande_enrichissement`, et `apply_enrichissement.py` les reprojette en
fin de pipeline.

---

## 7. Qui fait quoi

| Personne | Rôle | À solliciter pour |
|---|---|---|
| **Marlène MONTBRIZON** | Responsable Achats | Utilisatrice principale, signature des commandes |
| **Andréa JAMET** | Assistante Achats — **part le 31/07** | Fiche achat, sourcing interne, codes couleurs |
| **Maxence** | Reprend la boîte mail d'Andréa | Continuité des fils fournisseurs |
| **Eric T.** | Commerce | Décision de non-conformité, choix fournisseur, marquage, pantone |
| **Julia** | TB China | Fournisseur (plus fiable qu'Eric sur ce point), qualité acier, dimensions, **packing list** (envoyée par mail) |
| **Clarisse** | Design / Artwork | Artworks, pantone officiel, emplacement de marquage, packaging existant |
| **Emmanuelle** | Référentiel article | Création du code article |
| **Jonathan** | Design produit | Plans, dimensions, visuels nouveaux produits |
| **Marie** | Qualité | Rapports d'analyses |
| **Olivier** | Appro / GDD | Suggestions d'appro, circuit prototype GDD |
| **Samuel** | IT Réseau / Nubo | Windows Server, VPN Stormshield, compte AD |
| **e.georgeon** | Supply Chain | Validation du schéma de données |
| **Stéphane GUILLAUMONT** | Direction | Arbitrages, limites MCP |

---

## 8. Contraintes de calendrier (Antho)

Formation DataScientest : **07/08**, **10-14/08**, puis récurrent septembre à
novembre 2026 à raison d'1 à 2 jours par semaine, jusqu'en 2027.
Congés : **17-31/08**, **28/09-02/10**, **24-31/12**.

Conséquence directe : **entre le 31/07 et le 01/09, la disponibilité est très
réduite.** Tout ce qui exige Andréa doit être fait avant le 31/07 ; tout ce qui
exige une présence soutenue d'Antho doit être fait avant le 07/08 ou reporté à
septembre.

---

## 9. Documents de référence

Ce plan est un document de pilotage : il dit quoi faire, pas comment. Le détail
vit ailleurs.

**Matière métier** — la source de tout ce qui est écrit au §5 et au §6.

| Document | Contenu |
|---|---|
| `docs/20260727_FicheAchat_Questionnaire_Sourcing_Andrea_COMPLETE_v1.md` | **Le plus précieux avant le 31/07.** Carte de sourcing d'Andréa : qui détient quelle information, et les pièges de chacun |
| `docs/20260721_FUSEAU_RetoursDemo14h_v1.md` | Notes brutes de la démo du 21/07, origine des 6 décisions métier |
| `docs/20260721_FUSEAU_Audit_RetoursMetier_v1.md` | Audit croisé des retours, avec les questions restées ouvertes |
| `docs/20260707_questionnaire_demo.md` | Questionnaire du 07/07 et réponses métier (Q1 à Q22) |
| `docs/cadrage_fiche_achat.md` | Cadrage de la Fiche Achat, structure du gabarit FOR-ACH-03-12 |
| `docs/backlog_ui_demo.md` | Backlog UI issu des démos |
| `docs/analytics_design.md` | Cadrage analytique : quels indicateurs, pour quelle décision |
| `docs/audit_excels_service_achat.md` | Audit des Excel du service et colonnes non exploitées |
| `docs/sources_gsheet_drive.md` | Profilage des sources gsheet et Drive, gotchas de données |

**Technique et exploitation.**

| Document | Contenu |
|---|---|
| `README.md` | Installation, architecture, commandes |
| `docs/modele_semantique.md` | Dictionnaire de données `achat.*` (à jour) |
| `docs/achat_schema.yaml` | Schéma machine-readable, régénérable par introspection |
| `docs/architecture_data.md` | Flux de données global TB Groupe |
| `docs/20260723_FUSEAU_RunbookServiceWindows_v1.md` | Exploitation de la prod actuelle, accès LAN, logs, dépannage |
| `docs/20260727_FUSEAU_Procedure_Deploiement_WindowsServer_v1.md` | Migration serveur à venir |
| `docs/20260622_FUSEAU_RunbookOAuthGmail_v1.md` | Re-consentement OAuth Gmail |
| `docs/20260702_audit_champs_sylob_v25.md` | Champs disponibles côté Sylob V25 |

⚠️ Quatre documents sont **désalignés du code** et ne doivent pas être suivis à
la lettre : voir §4.2.

---

## 10. Journal

Une ligne par séance, la décision retenue uniquement. Le détail est dans git et
dans `05_ARCHIVES/Versions_Anterieures/`.

| Date | Retenu |
|---|---|
| 03/06 | Board post-its équipe Achats : recensement des manques du modèle de données |
| 08/06 | Premier état d'avancement ; 3 blocages identifiés (PJ Gmail, source transitaire, accès boîte Andréa) |
| 10/06 | Décision fondatrice : le DWH est la source de vérité, `achat.commande` en full-refresh, saisies utilisateur isolées dans `commande_annotation` |
| 23/06 | Première démo métier. Retours : désignation article, acompte versé, CA borné à 3 ans, lien Drive par n° d'inspection |
| 25/06 | Démo 2. Acompte et CA fournisseur livrés. Devise USD actée pour toutes les sources |
| 29/06 | Déploiement sur le poste de Marlène terminé. Plan A (PJ Gmail) prêt |
| 30/06 | Write-path Gmail pattern A acté : jamais d'écriture directe dans `commande`, tout passe par `ot_transport`. Ingestion Matrice TB Import (1198 articles) |
| 02/07 | Captation des Excel non exploités. Découverte : les PDF SPECTRO n'ont aucune couche texte, OCR obligatoire. Migration Python 3.11 |
| 07/07 | Démo métier. Retard redéfini (ETD réel − ETD confirmé). Historique prix : décision de désinvestir au profit de Sylob natif. Règle de paiement BL + 15 j |
| 20/07 | Correction du calcul de retard déployée. Design System TB appliqué au frontend. Ticket GLPI `svc-dataachat` envoyé |
| 21/07 | Démo 14h. Onglet Conteneurs livré. Revirement sur les doublons fournisseurs (regroupement par `frn_code`). Périmètre Article élargi à la vue 360° |
| 22/07 | Session poste Marlène : resync git, OCR installé, premier write en production (`ot_transport` 90 → 127), automatisation de l'ETL Gmail, 4 tables événements |
| 23/07 | **Mise en production.** Onglet Article et Fiche Achat Phase A. Doublons fournisseurs et filtre Promo implémentés |
| 27/07 | Session Antigravity : Fiche Achat Phase B (export PDF et xlsx), ingestion des ETA transitaires, rapprochement des réceptions Sylob, badges de provenance |
| 28/07 | Reprise et correction de la livraison Antigravity : 5 modules orphelins câblés, table `commande_enrichissement` (survit au full-refresh), étape ENRICH du pipeline. GRANT `public.articles3` obtenu, la recherche article voit enfin les 33 061 articles Sylob. Date de paiement saisissable. Fusion des trois traceurs dans ce document |
| 28/07 (après-midi) | Branchement de l'ETL sur le partage réseau via le compte de service AD. Trois pannes silencieuses corrigées derrière : mauvais fichier IMPORT résolu par un motif trop large, fichier transitaire passé de 18 à 14 colonnes donc plus aucune mise à jour d'ETA, colonne de travail bloquant le chargement avant qualité et acompte. ETL rejoué en production. Refonte de la fiche Article 360 en cartes et grille alignée. Accès LAN d'Andréa préparé depuis le poste de Marlène, reste la règle de pare-feu qui exige des droits administrateur |
| 28/07 | **Levée des réserves métier & infra** : réponses validées pour Q-A à Q-F (priorité DS, quarantaine Bext, PO critique = conteneur bloquant, BE GDD pour plans de prod, Clarisse/Andréa pour emballage). Purge définitive de l'ancien Sylob 102.21:5433 au profit de 102.41:5432. Compte AD `svc-dataachat` confirmé. |
| 28/07 (soir) | Deux règles métier corrigées après relecture : la conformité qualité est actée **par mail** comme la non-conformité, et la packing list vient de **TB China par mail**, pas de la Fiche Achat. Les deux ont une conséquence directe sur le périmètre de captation Gmail |
