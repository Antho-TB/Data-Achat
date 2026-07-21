# Retours démo métier 14h — 21/07/2026

> Récupérés en direct pendant/après la démo. Légende : ✅ fait (cette session) · 🟡 décision métier requise avant dev · ⬜ chantier à planifier · 🔬 investigation technique requise (pas un simple dev).

---

## ✅ Traité cette session (21/07, après-midi)

- **Suivi commande — filtre cassé** : `filterCommandes()` référençait `f-po` et `f-designation`, deux champs absents du HTML → plantait AVANT même de tester fournisseur/article/statut, donc aucun filtre ne marchait. Ajout des 2 barres de recherche (N° commande, désignation) + garde défensive sur `f-acompte`.
- **Historique de prix — recherche par désignation** : ajoutée (Fournisseurs > Détail, et onglet Article existant).
- **Précision des prix** : passés de 2 à 3 décimales partout (Suivi commande, Fournisseurs, Article).
- **KPI Retards** : le "77" (nb d'articles) n'était pas parlant et sans unité. Dashboard : le graphique "Retards par fournisseur" affiche maintenant le **retard maxi constaté (jours)** par fournisseur au lieu du nombre d'articles (avec légende ⓘ). Tableau Fournisseurs : colonne "Retards" relabellisée avec unité ("X art."), tooltip complet ajouté sur "Retard moy. (j)" expliquant la méthode (figé, moyenne 12 mois glissants, avances planchées à 0).
- **Suivi commande — colonne "Dernier évènement"** : tooltip ajouté avec le détail réel (quel champ a été modifié manuellement, ou quel statut logistique a été atteint), pas juste "manuel/auto" générique.
- **Artwork — commentaire tronqué** : tooltip natif ajouté sur la cellule (survol = texte complet).
- **Artwork — écart `artwork_en_attente`** (KPI=1 vs 8-9 lignes réelles gsheet) : corrigé. Les lignes "PAS DE REF" de l'onglet "Artworks en attente" ne sont plus jetées par le transform (code provisoire `NOUVEAU-<slug designation>`). Effet de bord positif : ~153 autres articles validés qui n'avaient jamais de ligne `achat.artwork` (jamais commandés) sont aussi redevenus visibles (`artwork_total` 792→951, `artwork_valides` 374→523).

## 🔬 Anomalie trouvée en creusant les retards (à vérifier, pas encore corrigée)

- **WANXIN : retard maxi = 444 jours**. C'est un chiffre extrême, probablement une anomalie de donnée (ETD confirmé mal saisi, ou ligne très ancienne jamais clôturée dans l'Excel) plutôt qu'un vrai retard. `nb_articles_en_retard` = 0 pour WANXIN (donc ce n'est plus un cas actif), mais à vérifier avant de citer ce chiffre.

---

## 🟡 Décisions métier requises avant dev (deadline Andréa 31/07)

1. **Statut "Livrée"** : aujourd'hui saisi manuellement dans l'Excel IMPORT (aucun rapprochement Sylob). Demande : rapprocher avec Sylob (réceptionné / entrée en stock) et afficher en plus la **Conformité / Non-conformité** (contrôle Qualité à réception). Nécessite de savoir : quelle table Sylob porte la date de réception réelle par PO/article ?
2. **Raison du retard** : à extraire des corps de mail (parsing), pas de saisie structurée existante. Rejoint le chantier "non-conformité par mail" déjà identifié (Q1-2 de l'audit du 07/07).
3. **Doublons fournisseurs** : ⚠️ **revirement** par rapport à la décision actée le 25/06 ("GUANGWEI = DIAMOND TRACK, comportement correct, rien à corriger"). Aujourd'hui signalé comme un vrai doublon à corriger : refaire le lien via l'**ID fournisseur Sylob** (`frn_code`), pas sur le nom texte. Idem **SMART IRON = JIT GLOBAL**. Nécessite d'auditer la table de mapping nom↔frn_code (probablement dans `enrich_ca.py` / `enrich_from_sylob.py`) et de vérifier s'il existe d'autres doublons du même type.
4. **Qualité — pas de code article dans les rapports d'inspection** : proposition métier = le service Qualité nomme désormais les PDF de rapport avec le code article dedans (convention de nommage à définir avec eux). Pas un dev FUSEAU, une évolution de process côté Qualité.
5. **Promo/Opé — filtre trop large** : aujourd'hui semble inclure tout ce qui commence par "Appro". Demande : ne garder que ce qui commence par **OP** ou **NOUVEAU**, et ajouter un champ **PRIORITAIRE (Oui/Non)** distinct du filtre texte. Nécessite un point avec Andréa/Marlène sur la définition exacte de "prioritaire".
6. **Fiche Achat — sources de vérité** (précision importante, à documenter dans `docs/cadrage_fiche_achat.md`) :
   - Données standards + logistiques (**EAN, PCB**) → **Sylob** est la source de vérité.
   - Tout le reste (marquage, matière, packaging détaillé...) → la **fiche achat existante** (PDF/xlsx `PS-*`) reste la source de vérité tant qu'elle n'est pas remplacée.
   - **Onglet Article** = vue à 360° de l'article (Sylob + Matrice TB Import + données Fiche Achat), pas juste l'historique prix.
   - **Onglet Fiche Achat** = consultation des fiches existantes + génération PDF + mise à jour des fiches existantes (pas la création ex nihilo qu'on avait cadrée initialement).
   → Ces 2 derniers points changent le périmètre fonctionnel des onglets Article et Fiche Achat tels que conçus aujourd'hui. À retrancher avant de continuer le dev de ces onglets.

---

## ⬜ Chantiers à planifier (scope clair, pas encore démarrés)

### Suivi commande
- Différencier dans la table `commande` le **statut de paiement** (payé/non payé) de l'**état de la commande** (actuellement conflaté dans un seul champ `statut`).

### Prévisionnel
- Vue prioritaire = **par livraison / par conteneur / par mois** (pas juste une liste de lignes).
- Marlène doit pouvoir voir en un coup d'œil les **N° de B/L en attente ou bloqués**, groupés par conteneur puis par fournisseur (cas d'usage : débloquer plusieurs conteneurs en payant plusieurs fournisseurs d'un coup).
- Vue "déjà payé" : par fournisseur sur 12 mois glissants, **mais aussi** par conteneur et par B/L.
- **Alertes changement ETA** : remonter vers la carte "Actions prioritaires" du Dashboard dès qu'un ETA change. Mise en forme conditionnelle progressive suggérée : 1er changement = orange, 2e = rouge, 3e = violet (nécessite de tracker l'historique des changements de date, pas juste la valeur courante).

### Qualité
- Une fois la convention de nommage actée avec le service Qualité (cf. point 🟡 4), brancher le parsing du numéro de rapport → code article.

### Article
- Ajouter une colonne **"Artwork (Oui/Non)"** — probablement une jointure simple sur `achat.v_artwork`.

### Fiche Achat (aperçu live construit cette session, compléments demandés)
- Ajouter l'**emplacement du marquage** (zone sur le produit, pas juste le texte et les dimensions).
- Ajouter le **bloc légal complet** (texte AGEC déjà présent en résumé dans l'aperçu, demande = le texte intégral réglementaire).
- Ajouter **N° de commande** et **N° de lot** (actuellement absents du formulaire).
- Ajouter **HO Code** (optionnel, utilisé par certains distributeurs type Carrefour) dans le bloc données logistiques.
- Clarifier **Name** (désignation étrangère/anglaise, celle de Sylob) vs **Désignation FR** (déjà un champ séparé côté FUSEAU, à bien mapper).
- Intégrer le **logo Design System** (actuellement un bloc texte "TB" approximatif, un vrai asset logo serait plus fidèle).
- Note repère : les fiches ont commencé en 2023 (avant elles étaient sur fond vert) — utile si un jour il faut dater/migrer les anciennes fiches.

### Artwork
- **Source de vérité confirmée** : gsheet `LIS-CON-28-0 Suivi des artworks-import`. Reprendre exactement les noms de colonnes et les formats de date utilisés dans ce gsheet (actuellement le transform normalise déjà les dates FR hétérogènes, mais les libellés affichés dans FUSEAU devraient coller au gsheet).
- Permettre l'**ajout de nouvelles lignes** depuis FUSEAU (un "simulateur de gsheet" côté UI) — implique d'écrire dans artwork_statut depuis le frontend, pas juste consulter.
- **Aperçu + lien cliquable vers le document Drive** correspondant à chaque ligne.

### Transverse
- Prévoir des **extractions régulières** (gsheet / Excel / PDF) au lieu de dépendre d'exports manuels ponctuels.
- Prévoir une **passe de vérification systématique sur les données Sylob** (au-delà du ponctuel déjà fait le 02/07) — cohérence article/fournisseur/EAN entre Sylob et les tables `achat.*`.

---

## Suivi

Prochaine étape suggérée : trancher les 6 points 🟡 avec Andréa/Marlène avant le 31/07 (surtout le point 3, doublons fournisseurs, et le point 6, sources de vérité Fiche Achat/Article, qui changent le périmètre de ce qui est déjà construit). Les chantiers ⬜ peuvent être planifiés indépendamment, aucun n'est bloquant pour le 31/07.
