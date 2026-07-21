# Audit des retours métier FUSEAU — checklist de run

> Croisement des prises de notes de démo (questionnaire 07/07 + relecture 20/07 + note Calendar 23/06 réintégrée le 21/07)
> avec l'état **réel du code** (vérifié le 21/07, pas le statut auto-déclaré).
> Sources : `docs/20260707_questionnaire_demo.md`, `docs/backlog_ui_demo.md`, note Google Agenda « Point Service Achat » du 23/06.
> Mise à jour 21/07 après-midi : lot de correctifs/polish (bug ETD/ETA, filtre Qualité, KPI Dashboard, badges Suivi commande, infobulles Qualité) + correctif définitif du bug artwork Validé=0 (2 bugs empilés : lecture xlsx incomplète + API ne lisant jamais la vue fusionnée) livrés et poussés sur `main`.
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
- **Q7 — EN RETARD (parti) vs (pas parti)** : badge visuel ajouté (rouge = pas parti = urgent, bleu = parti) avec tooltip. *(21/07 après-midi)*
- **Bug « Prochaines arrivées » ETD/ETA** : le bloc backend affichait ETA sous le libellé ETD ; code mort retiré (la vue était déjà remplacée par l'onglet Conteneurs, qui distingue correctement ETD/ETA/Livraison). *(21/07 après-midi)*
- **Backlog §6 — Qualité, filtre référence article** : champ ajouté (le backend le supportait déjà, filtre client). *(21/07 après-midi)*
- **Backlog §1 — Dashboard, statut Inconnu + déjà livré** : 2 KPI + tranche camembert ajoutés pour rendre visibles les lignes sans ETD (invisibles auparavant des deux compteurs En retard/Dans les délais) et les lignes livrées. Axes statut-retard / statut-commande déjà distincts (2 colonnes séparées). *(21/07 après-midi)*
- **Backlog §9/9bis — Lisibilité KPI** : généralisé (unité + définition sur toutes les cartes KPI Dashboard/Conteneurs) + infobulles ajoutées sur les en-têtes du tableau Qualité. *(21/07 après-midi)*

## 🟡 Partiel — fondation en place, reste à compléter/valider

- **KPI retard (investigation 21/07)** : le « retard » mesure surtout le **délai de consolidation** (PO confirmés sur plusieurs mois → même conteneur, même date de départ), pas la tardiveté fournisseur. WANXIN 102 j n'est pas un reproche fournisseur. → **à valider métier** (voir 🔬).
- **Backlog §5 — Prévi financier 2-3 mois (achat de dollar)** : échéancier `cash_echeances` en place ; manque la courbe/horizon dédié « combien de USD, quand ».
- **Backlog §3 — Cumul des retards fournisseur** : vue à jour (21/07), à **revalider à l'écran**.
- **Backlog §7 — Fiche Achat** : onglet + formulaire pré-rempli (Phase A) faits ; **génération PDF/xlsx (Phase B) à faire** ; questionnaire de sourcing Andréa prêt, **à faire remplir avant le 31/07**.

## ⬜ Reste à faire — remonté métier, pas encore implémenté

- **Backlog §2 — Suivi commande** : redéfinir « Dans les délais » et reprendre les **codes couleurs d'Andréa** — aucune spec écrite disponible, à capter en direct avec elle avant le 31/07 (pas de statuts manquants ni d'infobulle trouvés manquants à la relecture du 21/07 après-midi, corrigé si un cas concret ressort en démo).
- **Backlog §5 — Prévisionnel** : lever l'ambiguïté « à payer EN RETARD » (paiement ou livraison ?) — voir 🔬 ci-dessous, liée à la sémantique ETD confirmé.
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

- **Q13 — Paiement = liasse BL + facture + packing list** : `n_bl`/`n_facture` existent (colonnes commande/ot_transport) mais **aucune colonne packing list nulle part dans le schéma**, et `est_a_payer` ne vérifie aujourd'hui ni BL ni facture (seulement `date_paiement IS NULL`). Avant de coder : d'où viendrait la donnée packing list (parsing mail comme le BL, saisie manuelle) ? Qui la fournit ? *(pas codé le 21/07 — invention d'une colonne sans source identifiée aurait été un choix arbitraire)*
- **Q10-12 — Code article & prototype (Circuit A)** : relation plusieurs-à-plusieurs prototype↔code ; explorer le **« code affaire » GDD** comme modèle d'ID prototype ; ID prototype unifié à arbitrer avec Olivier ; Q11 (données circulant avant le code article) non répondu.
- **Sémantique `etd_confirme` / consolidation conteneur** (nouveau, issu de l'investigation 21/07) : à capter auprès d'**Andréa avant le 31/07** — définit-on l'ETD confirmé comme une date de départ ferme ou l'ETD initiale de commande ? Qui décide du groupage des PO dans un conteneur ?
- **[23/06] Statut de réception "actif" jusqu'à fin de contrôle qualité** (quarantaine) : changement de modèle de statut (une commande reçue reste "active"/en quarantaine tant que le contrôle qualité n'est pas clos) -- à cadrer avec Andréa/Marlène avant d'implémenter, impacte le modèle `commande`/`qualite_suivi`.
- **[23/06] Alertes imprévu majeur** (grève, incident logistique) : aucune source de donnée identifiée aujourd'hui (pas de flux "événement transport") -- à qualifier : alerte manuelle, flux transitaire, ou API tierce ?
- **[23/06] Chemin critique sur le suivi de commande** : notion à définir avec le métier (qu'est-ce qui rend un PO "critique" -- délai, valeur, conteneur bloquant ?) avant de coder un algorithme de plus court chemin.

---

## Synthèse

La quasi-totalité des items **codables sans arbitrage métier** est traitée (session du 21/07, matin + après-midi). Les chantiers réellement ouverts se regroupent en quatre blocs :

1. **Sémantique à capter avec Andréa avant le 31/07** : ETD confirmé/consolidation conteneur (KPI retard, ambiguïté « à payer EN RETARD »), codes couleurs et redéfinition « Dans les délais » du Suivi commande, code article/prototype (piste « code affaire » GDD).
2. **Données manquantes à la source** (avant de coder) : packing list comme déclencheur de paiement (Q13), mail de rejet Eric T pour la non-conformité (Q1-2), flag promo/urgence.
3. **Constructions substantielles non démarrées** (scope validé, à planifier) : onglets Article et Promo, HITL, génération PDF/xlsx de la Fiche Achat (Phase B), courbe dédiée du prévisionnel financier.
4. **À revalider à l'écran** : cumul des retards fournisseur (vue mise à jour le 21/07).

_Généré le 21/07/2026, mis à jour le 21/07/2026 après-midi (lot de correctifs + reclassement des items selon ce qui a pu être codé sans arbitrage métier)._
