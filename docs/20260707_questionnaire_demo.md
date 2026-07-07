# Questionnaire démo FUSEAU — 07/07/2026, 14h

> Support d'entretien pour la démo équipe métier (Andréa, Marlène, Olivier, Emmanuelle,
> Eric/Charles/David selon présents). Objectif : lever les zones d'ombre du modèle
> avant le départ d'Andréa (31/07). **Réponses collectées en démo intégrées ci-dessous.**
> Les actions techniques qui en découlent sont listées dans `plan_action.md`,
> section "Décisions actées en démo — 07/07".

---

## 1. Qualité — conformité et analyses

1. **Où vit la décision "conforme / non conforme"** après une analyse labo (chrome, dureté) ?
   ✅ **Réponse : dans le corps du mail.** Conforme = validé (pas de mail formel
   nécessaire). **Non conforme = Eric T (Commerce) est décideur, par mail explicite.**
   → Asymétrie importante : on ne peut détecter une non-conformité qu'en repérant un
   mail de rejet d'Eric T, pas une validation positive systématique. Implication
   technique : parsing du corps de mail (boîte Eric T), pas l'OCR PDF SPECTRO.

2. Qui valide cette conformité, et est-ce la même règle pour tous les types d'analyse ?
   ✅ Voir réponse 1 — Eric T décide par mail en cas de non-conformité.

3. Le dossier **GDD** a-t-il la même structure que TB (`Inspection`/`Reports of analysis`) ?
   ✅ **Non.** GDD est un **circuit distinct**, moins d'analyses, process moins formalisé.
   → Ne pas essayer de généraliser `crawl_drive_qualite.py` à GDD avec la même logique
   que TB ; à traiter séparément si besoin, priorité basse.

4. La colonne `hardness_hrc` vide sur les 8 rapports pilotes — normal ou anomalie ?
   ✅ **Normal.** Test de dureté fait **uniquement sur les couteaux**, pas sur les
   semi-produits ni les "couverts" (lg herit, échantillons pilotes = pas des couteaux).
   → Confirme que laisser `hardness_hrc` NULL était la bonne discipline (pas une donnée
   manquante à corriger, une absence de test légitime pour ce type de produit).

## 2. Historique prix — doublon Sylob ?

5. Qu'est-ce que FUSEAU apporte que Sylob n'a pas facilement ?
   ✅ **Rien de suffisant — décision : formation de l'équipe sur Sylob directement**,
   plutôt que de maintenir la fonctionnalité "Historique prix" côté FUSEAU.

6. Faut-il désinvestir cette fonctionnalité ?
   ✅ **Oui, implicitement** — cf. réponse 5. Ne pas prioriser de nouveaux
   développements sur l'historique prix FUSEAU (le fix désignation du 07/07 reste
   utile en attendant la transition, mais pas d'investissement supplémentaire).

## 3. Suivi commandes — retards

7. La distinction "EN RETARD (parti)" vs "(pas encore parti)" correspond-elle au besoin ?
   ✅ **Le fond est bon, mais l'UI/UX est à revoir** (présentation actuelle jugée pas
   assez claire/actionnable en l'état).

8. Le calcul du retard cumulé (figé à la livraison, exclu si clôturée) est-il le bon ?
   ⚠️ **Correction du calcul** — ce n'est PAS (date_livraison − ETD). La vraie règle :
   **retard = ETD réel − ETD confirmé**, moyenne calculée **par fournisseur, par an,
   sur 12 mois glissants**. Le retard doit être **figé à l'ETD** (une fois l'ETD réel
   connu, on ne recalcule plus en continu contre la date du jour).
   → **Action technique : revoir la requête de calcul du retard** (`v_retard_article`
   et tout ce qui en dépend) — la logique actuelle dans le code ne correspond pas à
   cette définition, à vérifier et corriger.

9. Qui doit pouvoir éditer la raison de retard (commentaire) ?
   ✅ **Tous ceux qui ont un mot de passe** (pas de restriction de rôle à implémenter).

## 4. Code article et prototype (Circuit A)

10. À quel moment précis la demande de code article arrive-t-elle réellement ?
    ✅ **Très tôt, via des conversations informelles dans Gmail (boîte Eric T)** — pas
    une demande formelle. Le vrai problème structurel soulevé : **c'est une relation
    plusieurs-à-plusieurs** (plusieurs prototypes/conversations pour un code, ou
    inversement). Piste évoquée : regarder comment **la BDD GDD gère le "code affaire"**
    — pourrait être un précédent/modèle réutilisable pour l'ID prototype.
    → **Action : explorer la structure "code affaire" dans la BDD GDD** (Sylob ou
    autre système GDD) avant de concevoir l'ID prototype unifié.

11. Quelles données circulent déjà avant la création du code article ?
    ⏳ Non répondu en démo — à reposer.

12. Faut-il un ID prototype unifié ?
    ⏳ Non tranché en démo — toujours à voir avec Olivier (cf. point 10 : la piste
    "code affaire GDD" est un nouvel élément à apporter à cette discussion).

## 5. Paiement / conteneur

13. Le paiement se déclenche au BL ou à un autre document ?
    ✅ **BL + facture + packing list ensemble = liasse documentaire complète.** Le
    modèle de données pour la vue paiement par conteneur doit lier les 3 documents,
    pas juste le BL seul.

14. Qui pose le flag promo/urgence, et à quel moment ?
    ✅ **À la commande, ou parfois en milieu de circuit** (déclenché par une vente
    commerce en cours de route). → Le flag doit être **modifiable à plusieurs étapes**,
    pas figé à la création.

15. Règle de retard de paiement — quelle date de référence ?
    ✅ **Théorie : ETD du BL. En réalité : +15 jours de tolérance.** Le retard de
    paiement ne doit compter **qu'au-delà de ETD_BL + 15 jours**.
    → **Action technique : implémenter cette règle** (date_reference_paiement =
    etd_bl + 15j) dans le futur module paiement/conteneur.

## 6. Nouveaux onglets — Article / Promo

16. Onglet Article — périmètre exact ?
    ✅ **Confirmé : suivi du changement de fournisseur dans le temps.** Le reste
    (stock, cycle de vie) relève de la **Supply Chain**, explicitement **hors
    périmètre Achats/FUSEAU**.

17. Onglet Promo — quels types d'opérations couvrir ?
    ✅ **Oui pour tout** (fidélité, promo ponctuelle, commande initiale nouveau client
    type COSTCO) — périmètre large validé, à cadrer avec des exemples concrets au
    moment du design.

## 7. Accès et fraîcheur des données (POC → prod)

18. L'IMPORT Excel du 10/06 est-il encore à jour ?
    ⏳ Non répondu en démo — à vérifier/rafraîchir avant la validation finale.

19. Accès à la boîte Gmail d'Andréa confirmé avant le 31/07 ?
    ⏳ Non répondu en démo — **reste bloquant**, à relancer avant le départ d'Andréa.

20. Accès réseau au dossier `2026 SUIVI MARITIME.xlsx` obtenu ?
    ⏳ Non répondu en démo — `ot_transport` reste en mode dégradé jusqu'à confirmation.

## 8. Divers / arbitrages ouverts

21. GUANGWEI et DIAMOND TRACK (même code Sylob) — un seul fournisseur ou un alias ?
    ✅ **C'est le même fournisseur.** Le comportement actuel (CA cumulé partagé) est
    donc **correct**, pas un bug à corriger — pas d'alias nécessaire.

22. Tous les montants sont-ils bien en USD, toutes sources confondues ?
    ✅ **Confirmé, oui, tout est en USD** (IMPORT, Sylob, acompte).

---

## Points encore ouverts après la démo (à relancer)

- Q11 (données pré-code-article), Q12 (ID prototype unifié — enrichi par la piste
  "code affaire GDD" de Q10)
- Q18 (fraîcheur IMPORT), Q19 (accès Gmail Andréa — **bloquant deadline 31/07**),
  Q20 (accès dossier maritime)

**Note d'usage d'origine** : prioriser 1, 5-6, 7-9 et 19 si le temps est compté —
conservé pour référence, la démo a effectivement couvert 1, 3-4, 5-6, 7-9 en profondeur ;
19 (le plus critique deadline) n'a pas été traité, à relancer en priorité.
