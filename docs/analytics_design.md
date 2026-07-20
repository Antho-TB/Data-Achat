# FUSEAU — Cadrage analytique (indicateurs & dataviz par onglet)

> Vision Data Analyst / Business Analyst : partir des **questions métier** de chaque
> utilisateur (Achats import, direction, cash), puis choisir l'indicateur et le visuel
> qui y répondent. Créé le 2026-07-20.
> Principe : un visuel = une décision. Pas de graphe « parce qu'on peut ». Chaque KPI
> porte une unité et une définition (cf. règle de lisibilité).

---

## Constat de départ

- Les statuts sont **pauvres et conflatés** : `statut_retard` est majoritairement INCONNU sur les lignes ouvertes, et `statut commande` mélange 3 axes orthogonaux (paiement, logistique, cycle). D'où des camemberts illisibles.
- Les 3 axes réels à séparer : **Paiement** (à payer / payé / payé en retard), **Logistique** (pas parti / en transit / livré), **Qualité** (en inspection / conforme / NC).
- La vraie valeur du service = **tenir les délais fournisseurs, ne pas bloquer un conteneur faute de paiement, sécuriser le cash USD, garantir la qualité**.

---

## Dashboard (pilotage / direction)

**Questions** : où est mon argent ? qu'est-ce qui brûle aujourd'hui ? quelles actions ?

| Indicateur | Unité | Pourquoi |
|---|---|---|
| Valeur en transit | USD | Capital engagé en mer, exposition |
| À payer sous 30 j | USD | Anticiper l'achat de dollar |
| Conteneurs en transit | nb | Charge logistique à venir |
| Taux de livraison à l'heure (OTD) | % | Santé fournisseurs en 1 chiffre |
| Retard moyen fournisseur (12 mois) | jours | Tendance fiabilité |
| Lignes actionnables aujourd'hui | nb | Ce qui nécessite une action |

**Dataviz** : (1) **Carte Actions prioritaires** (cf. chantier 8), (2) **courbe À payer par mois** sur 3 mois (cash forecast USD), (3) barres **retard moyen par fournisseur** (top 8), (4) **funnel du cycle** Acheté → Payé → Parti → Livré (volumes + fuites).
➡️ **Supprimer le camembert `statut_retard`** (données pauvres, non décisionnel).

## Suivi commandes (opérationnel)

**Questions** : quelles lignes nécessitent une action, et laquelle ?

| Indicateur | Unité |
|---|---|
| Lignes en attente de départ (ETD dépassé, pas parti) | nb |
| Lignes en transit | nb |
| Lignes à réceptionner (arrivées, pas livrées) | nb |
| Aging du retard (0-30 / 30-60 / 60+ j) | nb par tranche |

**Dataviz** : **histogramme empilé** « statut commande × en retard / à l'heure » (le double histogramme demandé, nécessite d'exposer les axes orthogonaux) ; **aging bar** des retards par tranche. Remplace le camembert.

## Fournisseurs (performance & risque)

**Questions** : qui est fiable ? qui est un risque (gros volume + peu fiable) ?

| Indicateur | Unité |
|---|---|
| Retard moyen (12 mois glissants) | jours |
| Taux OTD | % |
| CA 3 ans | USD |
| Lignes / montant en retard | nb / USD |

**Dataviz** : **nuage de points CA (x) vs retard moyen (y)** → repère en un coup d'œil les fournisseurs à fort CA et fort retard (risque prioritaire) ; scorecard triable. Barres retard moyen top N.

## Prévisionnel — FINANCIER (cash / change)

**Questions** : combien vais-je payer, quand, en USD ? quoi arbitrer pour ne pas bloquer un conteneur ?

| Indicateur | Unité |
|---|---|
| À payer 30 / 60 / 90 j | USD |
| À payer en retard | USD |
| Exposition USD totale | USD |

**Dataviz** : **barres/courbe À payer par mois** (horizon 3 mois, pour l'achat de dollar) ; **répartition du à-payer par conteneur** (arbitrage de déblocage) ; waterfall du cash. Le logistique quitte cet onglet (va dans Suivi conteneurs).

## Suivi des conteneurs (logistique) — nouvel onglet

**Questions** : quoi arrive quand, quoi bloque, pour qui ?

| Indicateur | Unité |
|---|---|
| Conteneurs en transit | nb |
| Valeur en transit | USD |
| Retard moyen ETD → ETA | jours |
| Prochaines arrivées 30 j | nb / USD |

**Dataviz** : **timeline / Gantt ETD → ETA → livraison** par conteneur ; barres **arrivées par semaine** ; répartition par destinataire (Pommier / GDD).

**Prévisionnel conteneurs M → M+3** (demandé) : vue des arrivées (ETA) regroupées par mois sur le mois courant et les 3 suivants, avec **nb conteneurs + valeur USD par mois**. Double lecture : logistique (charge de réception à venir) et financier (montant à décaisser par mois → planifier l'achat de dollar). C'est le pont entre l'onglet Conteneurs (logistique) et le Prévisionnel financier.

## Qualité

**Questions** : taux de conformité, quels fournisseurs à risque qualité ?

| Indicateur | Unité |
|---|---|
| Taux de conformité | % |
| Nb NC / FAIL | nb |
| Délai moyen d'inspection | jours |

**Dataviz** : **jauge taux de conformité** ; **FAIL par fournisseur** (barres) ; **Pareto des défauts** (80/20).

## Artwork

**Questions** : qu'est-ce qui bloque le design ?

| Indicateur | Unité |
|---|---|
| Artworks en attente | nb |
| Ancienneté moyenne en attente | jours |
| En attente > 15 j (à relancer) | nb |

**Dataviz** : **aging** des artworks en attente (tranches de jours).

---

## Prérequis technique transverse

Pour rendre possible le cross-tab paiement × logistique et les vrais taux (OTD, conformité), il faut **exposer les axes orthogonaux** au niveau ligne (ils existent déjà en base : `v_previsionnel` a `est_achete / est_a_payer / est_parti / est_livre / est_a_payer_en_retard`). Étape 1 : enrichir l'endpoint `/api/commandes` avec ces booléens → débloque la plupart des viz ci-dessus sans nouveau calcul.
