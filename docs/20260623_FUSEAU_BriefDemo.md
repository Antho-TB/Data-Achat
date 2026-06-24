# Brief demo FUSEAU -- 23/06 14h

## Avant de lancer (2 min)
- `python run_api.py` -> http://127.0.0.1:5050 ; verifier `/api/health` = `connected`.
- Fermer l'onglet pgAdmin contenant les `DROP TABLE` (partage d'ecran).
- Ouvrir `docs/plan_action.md` en second.

## Pitch (30 s)
FUSEAU : l'ERP Achat import de TB. Une source UNIQUE branchee sur le DWH, a la place
des Excel eparpilles. Donnees reelles, 6 onglets par metier.

## Chiffres cles
- 1 198 produits | 636 lignes de commande | **4,0 M EUR** achetes (vrai montant, pas le surcompte Excel).
- 181 lignes en retard ; top fournisseurs : HONGXING, NOSKI.
- Qualite : 633 controles, 297 OK / 89 FAIL, NCR traces.
- 57 conteneurs suivis.

## Deroule (6 onglets)
1. Dashboard : KPIs + retards par fournisseur en un coup d'oeil.
2. Suivi commandes : statut PAR ARTICLE (pas par PO), filtres.
3. Fournisseurs : historique prix par article/fournisseur (besoin n1 d'Andrea).
4. Artwork : suivi design Clarisse (Envoye / Attente / Valide).
5. Qualite (nouveau) : evaluation fournisseurs (taux FAIL, NCR) + checkpoints MAT/SP/BAT.
6. Previsionnel enrichi (nouveau) : achete / a payer / en inspection / parti / en retard / livre,
   + ventilation par fournisseur.

## 3 messages a faire passer
- On objective ce qui etait dans la tete des gens : retards, prix, qualite fournisseur.
- Le retard se mesure PAR ARTICLE, pas par commande (demande metier integree).
- Prochain palier : email-first -- recuperer les PJ fournisseurs (proforma/BL) automatiquement.

## Honnetete (si on demande la suite)
Reste a faire : bornage de dates au choix, drill-down produit au clic, volet "suivi des
analyses" qualite par mail, branchement Gmail reel. Tout est dans le plan d'action.

## Si question infra/acces
L'acces DWH depend du reseau (resolu aujourd'hui). Cause et correctif durable documentes
et transmis a Samuel/Nubo (regle NSG `allow-vpn-to-postgresql` + route VPN nomade). Rien a
gerer cote metier.
