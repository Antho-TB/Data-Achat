# Backlog UI/UX FUSEAU — retours démo 07/07 + notes 20/07

> Consolidation des prises de notes d'Antho (démo métier du 07/07 et relecture du 20/07),
> croisées avec `docs/20260707_questionnaire_demo.md` et l'état du code.
> Légende : ✅ fait · 🟡 partiel · ⬜ à faire · 🆕 nouveau besoin (pas dans le modèle actuel).
> Créé le 2026-07-20.

---

## 0. Déjà traité (rappel)

- ✅ **Calcul du retard** corrigé et déployé (ETD réel − ETD confirmé, figé, moyenne fournisseur 12 mois glissants). ⚠️ **KPI à investiguer** : sortie suspecte (quasi 100% « en retard », WANXIN 182j) — que représente `etd_confirme` dans la donnée ? Effet du grain PO×article ?
- ✅ Montants en USD (relabel).
- ✅ Données rafraîchies (IMPORT 2026 + Matrice frais : 798 commandes, maritime chargé).

---

## 1. Dashboard

- ⬜ **Graph « statut Inconnu »** à traiter (1 commande en statut Inconnu après refresh) : soit reclasser, soit exclure du graph.
- ⬜ **Indicateurs manquants** pour les commandes : segmenter « en cours de livraison » en **(1) Dans les délais / (2) En retard**, et un indicateur **Déjà livré**.
- ⬜ **Confusion statut retard vs statut commande** dans les indicateurs : les deux axes doivent être clairement séparés (cf. décision 07/07 : KPI figé ≠ alerte opérationnelle).

## 2. Suivi de commande

- ⬜ **Redéfinir « Dans les délais »** : ne contient QUE les commandes en cours de livraison, dans les délais (date en infobulle). Sinon → statut **Livré**.
- ⬜ **Infobulles de définition** sur chaque indicateur / colonne de statut.
- ⬜ **UI/UX des statuts à revoir** : reprendre les **codes couleurs déjà utilisés par Andréa** (récupérer sa convention).
- ⬜ **Statuts manquants** : « en attente de livraison », « inspection en cours », « livré le … » (date en infobulle).
- ⬜ **Infobulle date d'inspection** (donnée déjà en base : `achat.qualite.date_inspection`).
- ⬜ **Tri par colonne**.
- 🆕 **Colonne N° conteneur** pour les commandes en cours de livraison qui en ont un → **clic sur le N° → onglet Suivi des conteneurs**. Source : Draft du BL (mail) puis BL officiel (conteneur sur quai / parti).
- ℹ️ **Modèle** : une commande peut être saisie en amont et ses lignes bougent dans le temps (qté et prix pendant la négo) — le modèle doit tolérer la mise à jour de lignes existantes.

## 3. Suivi fournisseurs

- ⬜ **Afficher les livraisons en retard** dans cet onglet.
- ⬜ **« Dernière activité » imprécise** : clarifier ce que c'est (date de livraison ? autre ?) et l'afficher explicitement.
- ⬜ **Vérifier le cumul des retards** (revalider avec la nouvelle vue `v_retard_fournisseur`).

## 4. 🆕 Nouvel onglet — Suivi des conteneurs

Colonnes : **N° conteneur · nom du bateau · N° BL · destinataire (Pommier / GDD / les 2) · ETD (départ Chine) · ETA (arrivée Fos) · date de livraison sur site · transitaire**.
Données déjà disponibles dans `achat.ot_transport` (maritime chargé) + BL (Draft puis officiel via ETL Gmail). C'est ici que vit le **prévisionnel logistique des livraisons** (à sortir du Prévisionnel financier, cf. §5).

## 5. Prévisionnel (doit devenir un prévi FINANCIER, pas logistique)

- ⬜ **« À payer EN RETARD 1,31 M USD » ambigu** : en retard de quoi, paiement ou livraison ? Les mesures ne précisent pas **quoi payer**.
- 🆕 **Déclencheur de paiement = le BL** (conteneur sur quai ou sur l'eau). Besoin d'**arbitrer quelle ligne d'article payer** pour ne pas bloquer un conteneur.
- ⬜ **Prévi à 2-3 mois** pour acheter du dollar au bon moment (objectif : couverture de change).
- ⬜ **« Prochaines arrivées » incohérent** : la colonne titrée ETD est en fait l'**ETA** ; l'article `10110035` est dans 2 conteneurs ; des dates de mars s'affichent alors qu'on attend des livraisons de juillet → **bug de sélection/dates à corriger**.
- ℹ️ Délai moyen ETD→ETA ≈ **60 jours**.
- ➡️ **Déplacer le prévisionnel des livraisons** vers l'onglet Suivi des conteneurs ; ne garder ici que le **financier** (quoi payer, quand, combien de USD).

## 6. Qualité

- ⬜ **Filtre par référence article** dans le suivi qualité par produit.

## 7. 🆕 Fiche Achat (nouveau chantier)

Intégrer la **Fiche Achat** dans FUSEAU : **consultation des fiches existantes + création de nouvelles**.
C'est une fiche récapitulative et détaillée d'un produit, base d'échange avec le fournisseur ET en interne. Tâche aujourd'hui portée par Andréa (part le 31/07 → à capter vite).
- Exemple de dossier : `Service_Achat/00182725-Heritage black et inox-NOSKI`.
- Templates existants : `Service_Achat/…FOR-ACH-03-12 Purchase sheet-Fiche Achat Vierge*.xlsx` (Produits uniques, Ménagères et sets).
- À cadrer : structure des blocs, stockage (table `achat.*` ? fichier ?), lien avec `code_article` / `article_nomenclature`, workflow de création (Circuit A).

## 8. Transverse — Fiabilité de la donnée

- ⬜ **HITL (Human-in-the-loop)** : ajouter un point de validation humaine quand il y a **conflit entre deux vérités possibles** (ex. date mail vs date Sylob, prix négocié qui bouge).

---

## Priorisation suggérée (à valider avec Antho)

1. **Quick wins UI Suivi commande** : tri colonnes, infobulles (inspection, définitions), redéfinition « Dans les délais », codes couleurs Andréa.
2. **Onglet Suivi des conteneurs** (données déjà en base, fort ROI, sort le logistique du prévi).
3. **Recadrage Prévisionnel financier** + correction bug « Prochaines arrivées » (ETD/ETA).
4. **Investiguer le KPI retard** (préalable à « cumul des retards » fournisseur).
5. **Fiche Achat** (chantier à part, cadrage d'abord — capter l'input d'Andréa avant le 31/07).
6. **HITL** (transverse, à intégrer au fil des onglets).
