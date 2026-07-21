# Audit des retours métier FUSEAU — checklist de run

> Croisement des prises de notes de démo (questionnaire 07/07 + relecture 20/07 + note Calendar 23/06 réintégrée le 21/07)
> avec l'état **réel du code** (vérifié le 21/07, pas le statut auto-déclaré).
> Sources : `docs/20260707_questionnaire_demo.md`, `docs/backlog_ui_demo.md`, note Google Agenda « Point Service Achat » du 23/06.
> Légende : ✅ fait & vérifié · 🟡 partiel · ⬜ à faire · 🔬 métier/recherche (pas du dev).
>
> ⚠️ Les occurrences du **14/07** et du **21/07** de « Point Service Achat » n'ont **aucune note enregistrée** dans l'événement Calendar — à vérifier que la démo a bien eu lieu / que les retours n'ont pas été pris ailleurs.

---

## ✅ Traité et vérifié (en prod / dans le code)

- **Q8 — Calcul du retard** : ETD réel − ETD confirmé, moyenne par fournisseur sur 12 mois glissants, figé. Déployé le **21/07** (`v_retard_expedition` / `v_retard_fournisseur`) + garde-fou erreurs d'année (180 j).
- **Q15 — Retard de paiement = ETD_BL + 15 j** : implémenté (`/api/previsionnel`, échéancier `cash_echeances`).
- **Q9 — Édition raison/statut retard ouverte à tous** (mot de passe, pas de rôle) : endpoint annotation + `X-API-Key`.
- **Q18 — Fraîcheur IMPORT** : rafraîchi le 20/07 (798 commandes, 1199 produits, matrice frais).
- **Q20 — Accès suivi maritime** : `ot_transport` chargé (SUIVI MARITIME, 90 lignes), plus de mode dégradé.
- **Q22 — Montants en USD** : confirmé toutes sources + relabel USD dans l'UI.
- **Q21 — GUANGWEI / DIAMOND TRACK** : même fournisseur, CA cumulé partagé = comportement correct (aucune action).
- **Q19 — Accès Gmail Andréa** : résolu (boîte transférée à Maxence, Marlène en copie systématique) → risque marginal (fils où Andréa répond sans Marlène).
- **Backlog §0bis — Carte « Actions prioritaires »** : livrée 20/07.
- **Backlog §4 — Onglet Conteneurs** + remplacement du « Planning par mois » : livré ; **colonne N° conteneur cliquable ajoutée le 21/07**.
- **Backlog §2 — Tri par colonne** (tous tableaux) : livré 20/07.
- **Q5-6 — Historique prix** : décision actée = désinvestir (formation Sylob), pas d'action supplémentaire.
- **Q4 — `hardness_hrc` NULL** : absence de test légitime (dureté sur couteaux uniquement), pas une anomalie.

## 🟡 Partiel — fondation en place, reste à compléter/valider

- **Q7 — EN RETARD (parti) vs (pas parti)** : le fond est affiché dans le tableau Suivi commande ; l'**UI/UX reste à revoir** (cf. §2 ci-dessous).
- **KPI retard (investigation 21/07)** : le « retard » mesure surtout le **délai de consolidation** (PO confirmés sur plusieurs mois → même conteneur, même date de départ), pas la tardiveté fournisseur. WANXIN 102 j n'est pas un reproche fournisseur. → **à valider métier** (voir 🔬).
- **Q13 — Paiement = liasse BL + facture + packing list** : `ot_transport` porte `n_bl` et `n_facture`, mais pas la packing list ni le lien « liasse complète » comme déclencheur de paiement.
- **Backlog §5 — Prévi financier 2-3 mois (achat de dollar)** : échéancier `cash_echeances` en place ; manque la courbe/horizon dédié « combien de USD, quand ».
- **Backlog §3 — Cumul des retards fournisseur** : vue à jour (21/07), à **revalider à l'écran**.
- **Backlog §9/9bis — Lisibilité KPI + dataviz** : partiellement fait (infobulles sur en-têtes, palette graphes alignée) ; à **généraliser** (unité systématique, définition sur chaque indicateur).
- **Backlog §7 — Fiche Achat** : onglet + formulaire pré-rempli (Phase A) faits ; **génération PDF/xlsx (Phase B) à faire** ; questionnaire de sourcing Andréa prêt, **à faire remplir avant le 31/07**.

## ⬜ Reste à faire — remonté métier, pas encore implémenté

- **Backlog §1 — Dashboard** : traiter le statut « Inconnu » (reclasser ou exclure) ; segmenter « en cours de livraison » en (dans les délais / en retard) + indicateur « déjà livré » ; séparer nettement axe statut-retard vs statut-commande.
- **Backlog §2 — Suivi commande** : redéfinir « Dans les délais » (uniquement en cours + dans les délais) ; reprendre les **codes couleurs d'Andréa** ; statuts manquants (attente livraison, inspection en cours, livré le…) ; infobulle date d'inspection ; infobulles de définition systématiques.
- **Backlog §5 — Prévisionnel** : lever l'ambiguïté « à payer EN RETARD » (paiement ou livraison ?) ; **corriger le bug « Prochaines arrivées »** (colonne titrée ETD = en fait ETA ; article 10110035 dans 2 conteneurs ; dates de mars parasites).
- **Backlog §6 — Qualité** : filtre par **référence article** (le tab n'a qu'un filtre fournisseur / résultat / BAT).
- **Q1-2 — Qualité non-conformité** : détecter le **mail de rejet d'Eric T** (parsing du corps de mail, boîte Commerce) — non couvert par le pipeline BL/PJ actuel (asymétrie : pas de validation positive systématique).
- **Q16 — Onglet Article** : suivi du changement de fournisseur dans le temps (périmètre validé, non construit ; stock/cycle de vie = hors périmètre, Supply Chain).
- **Q17 — Onglet Promo** : opérations promo / fidélité / nouveau client type COSTCO (périmètre large validé, non construit).
- **Q14 — Flag promo/urgence** : modifiable à plusieurs étapes du circuit (aucun flag promo dans le modèle commande actuel).
- **Backlog §8 — HITL** : point de validation humaine en cas de conflit entre deux vérités (date mail vs Sylob, prix négocié qui bouge).
- **[23/06] Colonne acompte versé** (Suivi commande / Prévisionnel) : les acomptes existent dans Sylob mais ne sont pas remontés dans FUSEAU -- certains fournisseurs réclament le total en oubliant un acompte déjà versé.
- **[23/06] Qualité — lien Drive par N° d'inspection** : cliquer sur un résultat FAIL doit ouvrir le rapport correspondant dans le Drive (nom du fichier = N° d'inspection) ; + colonne conformité de l'analyse labo (taux de chrome / dureté) rattachée au N° de commande.
- **[23/06] Suivi commande — désignation article** : afficher la désignation métier de l'article (pas seulement le code), c'est ce que le service Achats utilise au quotidien.
- **[23/06] Fournisseurs — CA borné dans le temps** : pouvoir afficher le CA fait avec un fournisseur sur les 3 dernières années (glissant), pas seulement le cumul total.

## 🔬 À trancher métier / recherche (pas du dev pur)

- **Q10-12 — Code article & prototype (Circuit A)** : relation plusieurs-à-plusieurs prototype↔code ; explorer le **« code affaire » GDD** comme modèle d'ID prototype ; ID prototype unifié à arbitrer avec Olivier ; Q11 (données circulant avant le code article) non répondu.
- **Sémantique `etd_confirme` / consolidation conteneur** (nouveau, issu de l'investigation 21/07) : à capter auprès d'**Andréa avant le 31/07** — définit-on l'ETD confirmé comme une date de départ ferme ou l'ETD initiale de commande ? Qui décide du groupage des PO dans un conteneur ?
- **[23/06] Statut de réception "actif" jusqu'à fin de contrôle qualité** (quarantaine) : changement de modèle de statut (une commande reçue reste "active"/en quarantaine tant que le contrôle qualité n'est pas clos) -- à cadrer avec Andréa/Marlène avant d'implémenter, impacte le modèle `commande`/`qualite_suivi`.
- **[23/06] Alertes imprévu majeur** (grève, incident logistique) : aucune source de donnée identifiée aujourd'hui (pas de flux "événement transport") -- à qualifier : alerte manuelle, flux transitaire, ou API tierce ?
- **[23/06] Chemin critique sur le suivi de commande** : notion à définir avec le métier (qu'est-ce qui rend un PO "critique" -- délai, valeur, conteneur bloquant ?) avant de coder un algorithme de plus court chemin.

---

## Synthèse

La grande majorité des retours métier est **traitée ou en fondation**. Les chantiers réellement ouverts se regroupent en trois blocs :

1. **Polissage UI Suivi commande / Dashboard / Prévisionnel** (statuts, infobulles, codes couleurs Andréa, bug « Prochaines arrivées »).
2. **Deux nouveaux onglets non construits** : Article (suivi fournisseur) et Promo.
3. **Deux sujets métier à capter avant le départ d'Andréa (31/07)** : sémantique ETD/consolidation et code article/prototype (piste « code affaire » GDD).

_Généré le 21/07/2026, mis à jour le 21/07/2026 (intégration note Calendar 23/06)._
