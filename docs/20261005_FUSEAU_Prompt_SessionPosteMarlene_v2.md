# Prompt pour la session Claude du poste de Marlène, deuxième passage (05/10/2026)

> Suite du compte rendu `FUSEAU_retours\20261005_CR_SessionPoste.md`.
> À coller tel quel dans la session Claude Code du poste de Marlène.
> L'étape 3 (factures témoins) se fait idéalement avec Marlène.

---

```text
Deuxième passage sur le poste de Marlène, dépôt C:\Users\mmontbrizon\Documents\Claude\Data-Achat. Mêmes garde-fous que le premier passage (relis-les dans docs\20261005_FUSEAU_Prompt_SessionPosteMarlene_v1.md), avec ces précisions :
- Tu as le droit de modifier le prompt de la tâche Cowork fuseau-gmail-threads-achat, après en avoir fait une copie de sauvegarde datée à côté (suffixe .bak_20261005). C'est la seule modification autorisée hors config\.env.
- Aucune écriture en base : tous les chargements se font en --dry-run. Ne crée PAS config\facture_auto.flag.
- Rien sur le réseau, le VPN, Azure. Pas de commit, pas de push, pas de suppression.
Le compte rendu va dans C:\Users\mmontbrizon\Documents\Claude\FUSEAU_retours\20261005_CR_SessionPoste_v2.md, et tu me colles aussi son contenu en fin de session.

ÉTAPE 1 : RÈGLE « PENDING » DANS LA TÂCHE COWORK
Constat en base : 13 décisions qualité dont le texte contient « Pending » sont enregistrées « conforme » (ou « non_conforme »). Exemples réels :
- « FRI 'Pending' ; OK SHIPMENT TB sous réserve de remplacement des produits » : DEKRA n'a pas tranché, mais TB a accordé l'expédition sous réserve.
- « Rapports FRI (4 items) statut 'Pending', expédition validée par le métier ».
Règle à appliquer :
- Rapport DEKRA « Pending » SANS décision TB dans le fil : decision = "en_attente".
- Rapport DEKRA « Pending » AVEC accord d'expédition TB (« OK shipment », « expédition validée », « sous réserve ») : decision = "conforme_sous_reserve", et le motif reprend la réserve telle qu'écrite (ex. « remplacement des défectueux »).
- « Pass » reste "conforme", « Fail » reste "non_conforme".
a. Trouve le prompt de la tâche Cowork (Get-ChildItem sur le dossier des tâches planifiées Claude du profil, ou interface Cowork) et la partie qui classe les décisions qualité. Sauvegarde-le.
b. Ajoute la règle ci-dessus, avec les deux exemples. Ne change rien d'autre dans ce prompt.

ÉTAPE 2 : DOUBLONS DE DÉCISIONS
Constat en base : des décisions identiques sont enregistrées plusieurs fois (même PO, même stade, même date, même motif). Exemple : 6 lignes identiques pour le PO 00017308, stade inspection, le 30/09 ; 2 pour le PO 00179321 le 28/07 ; 2 pour le PO 00184684 le 11/09.
a. Regarde comment la tâche Cowork appelle src\scripts\gmail\load_evenements.py et ce qu'elle met dans cle_idempotence (ou ce que _cle() calcule à sa place).
b. Explique pourquoi ces doublons passent le ON CONFLICT : une clé différente à chaque passage (horodatage, id de message différent pour le même mail cité dans plusieurs réponses du fil, ordre des items...) ?
c. Propose la correction (dans le prompt de la tâche ou dans le code), mais N'APPLIQUE une correction que si elle se limite au prompt de la tâche Cowork. Si c'est du code, décris-la précisément dans le compte rendu : Antho la fera en PR.

ÉTAPE 3 : NOUVELLE CATÉGORIE « INSPECTION RÉSERVÉE » (DEVIS DEKRA)
Tu as constaté que la boîte reçoit en copie le devis DEKRA, 1 à 9 jours avant l'inspection, et que la tâche Cowork ne le garde nulle part.
a. Ajoute au prompt de la tâche Cowork une catégorie : devis DEKRA d'inspection reçu => un événement domaine "qualite", stade "inspection", decision "reservee", date_info = DATE D'INSPECTION PRÉVUE (pas la date du mail), motif = « Devis DEKRA » suivi de la référence du devis si elle existe, po_number et code_article si le mail les donne (un événement par PO), texte = résumé d'une ligne (usine, fournisseur, date). Une seule fois par devis : clé d'idempotence fondée sur le thread et le PO, pas sur l'heure.
b. Teste la nouvelle consigne SANS écrire : rejoue la tâche sur tes 5 exemples (fichier FUSEAU_retours\20261005_Exemples_MailDekraReservation.md) jusqu'à produire le JSON d'événements, puis
   .\.venv311\Scripts\python.exe -m src.scripts.gmail.load_evenements --file <le json> --dry-run
   Recopie le JSON obtenu et la sortie du dry-run dans le compte rendu.
c. Colle aussi dans le compte rendu le contenu complet des 5 exemples (sans signatures ni téléphones) : Antho ne peut pas lire ce dossier depuis son poste.

ÉTAPE 4 : MONTANTS DE FACTURE, VALIDATION SANS ÉCRIRE
L'étape facture n'a jamais tourné (flag absent, 37 passages sautés). Suis l'étape 6 du runbook docs\20260731_FUSEAU_RunbookPosteMarlene_MontantsFacture_v1.md, en dry-run uniquement :
a. Mois récents : .\.venv311\Scripts\python.exe -m src.scripts.gmail.load_facture --folder data\PJ\202609 --dry-run, puis idem avec data\PJ\202610 s'il existe.
b. Relève : pièces reconnues comme comptables, pièces écartées, lignes [ATTENTION] ... ecart de X % (recopie-les), lignes [ATTENTION] ... confiance, lignes [ECHEC], durée totale, et le nombre d'appels au modèle si le journal le donne.
c. Cas témoins du runbook (facture HONGXING 6 403,20 EUR, note de crédit GUANGWEI négative, liasse JIT GLOBAL 19 557,72) : s'ils datent de juillet, lance aussi le dry-run sur data\PJ\202607 et dis si chacun ressort correctement. Si Marlène est présente, demande-lui 2 factures récentes qu'elle connaît et compare.
d. NE CRÉE PAS le flag et NE LANCE PAS de chargement réel : Antho décidera au vu de ton compte rendu.

ÉTAPE 5 : COMPTE RENDU
Même format que le premier passage : tableau de synthèse en tête, puis une section par étape (fait, chiffres, échecs avec message exact, non fait et pourquoi). Mets le diff exact apporté au prompt de la tâche Cowork (avant / après). Colle le compte rendu complet dans ta réponse finale.
```

---

## Ce qu'Antho fait ensuite

- Relire le diff du prompt Cowork et le JSON des devis DEKRA.
- Décider de l'activation des factures (création du flag) au vu des témoins.
- Requalifier les 13 décisions « Pending » en base selon la règle validée, et dédoublonner les décisions : migration SQL à préparer, avec archive.
- Afficher la réservation DEKRA sur Suivi commandes (« Inspection en cours » avec la date) et sur l'onglet Qualité.
