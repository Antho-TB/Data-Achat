# Profil source #4 — SUIVI MARITIME (Andréa, mail 25/06)

> Profilé le 2026-06-30 via le connecteur Drive (lecture du gsheet).
> Cible : `achat.ot_transport` (PK `n_conteneur`) — zone expédition, pattern A.
> Source faisant foi (prod) : serveur `\\Srv-files-pom\…\SUIVI CDES IMPORT\2026\TRANSITAIRE`.
> Copie lisible (POC) : gsheet `1hP73oivXrB8o8I7pkrGh7y6nPzn0ccfW` (partagé transitaire).

## Structure (1 feuille, 2 zones)

**Zone 1 — données conteneurs** (ce qu'on ingère). En-tête réel (après 2 lignes de bannière « FORTES CHALEURS… ») :

```
FOURNISSEUR | COMMANDE | REF QUALITAIR | TYPE | POL | POD | NAVIRE |
ETD | ETA | CONTENEUR | ATD | ETA(2) | BL | ORIGINAUX | DDL ESTIMEE |
DATE CONFIRMEE | HEURE | SITE | COMMENTAIRE
```

**Zone 2 — calendrier hebdo de livraison** (SEM 14 → SEM 53, double colonne TB / GDD) : **à IGNORER** (planning visuel, pas de la donnée conteneur).

## Mapping → achat.ot_transport

| Colonne sheet | → ot_transport | Règle |
|---|---|---|
| CONTENEUR | `n_conteneur` (PK) | trim espaces ; **exclure les lignes sans conteneur** (bookings futurs en attente) |
| BL | `n_bl` | peut contenir **plusieurs BL** (séparés espace) → 1er ou éclater |
| ATD (sinon ETD) | `etd_reel` | ATD = départ réel ; ETD = estimé (fallback) |
| ETA(2) confirmée (sinon ETA) | `eta` | **2 colonnes ETA** : col 9 estimée, col 12 confirmée/arrivée |
| DATE CONFIRMEE | `date_livraison` | date de livraison réelle |
| SITE | `lieu_livraison` | POMMIER / GDD |
| (constante) | `transitaire` | `QUALITAIR` (toute la feuille) |
| REF QUALITAIR | — | booking forwarder (SOFSI…), **pas** une facture |
| COMMANDE | (lien commande) | PO(s) — voir gotcha explosion |

## Gotchas (pièges de parsing)

1. **Dates textuelles mois anglais SANS année** (`28 December`, `6 March`, `25 July`) → inférer l'année. ⚠️ rollover déc→mars = année+1 (campagne import à cheval sur 2 ans).
2. **2 colonnes ETA** (estimée vs confirmée) — ne pas confondre ; prendre la confirmée en priorité.
3. **COMMANDE multi-PO** : `00162299/ 163764`, `PO00169477/174098/00017492`, annotations `(PP 231)`, préfixes `PO`/`GE#`/`TB#` → éclater + nettoyer (réutiliser `_clean_ref`).
4. **Lignes groupées** : une ligne sheet peut porter **plusieurs conteneurs/BL** pour un même navire → 1 enreg. ot_transport par conteneur.
5. **Fin de zone données** : s'arrêter à la 1ʳᵉ ligne du calendrier (`… SEM 14` / ligne sans conteneur valide après la dernière commande).
6. **Bannière** : ignorer les 2 premières lignes (horaires d'été).
7. **Bookings futurs sans conteneur** (`NOSKI TB#FUSION-PROMO`, `GE#PO00017938`) → pas de PK → hors ot_transport (à garder éventuellement pour un suivi « commandé pas encore embarqué »).

## Statut & prochaine étape

- ✅ Source lisible via connecteur Drive (prouvé 30/06). Bootstrap actuel `ot_transport` (57 lignes) vient de cette feuille.
- ⏭️ À construire : `transform_suivi_maritime(df) -> records` + branchement sur `load_ot_gmail` / `load_ot_transport`.
- 🔴 **Décision source de vérité** (une seule par table) : gsheet Drive (lisible maintenant, POC) **vs** serveur TRANSITAIRE xlsx (faisant foi, prod). À trancher avant de câbler.
