# Cadrage : droits par onglet et consultation des fiches achat (08/10/2026)

> Idées d'Antho du 08/10, après la réponse de Clarisse sur l'onglet Artwork.
> Rien n'est développé. Les décisions du §4 sont à prendre avant tout code.

## 1. Constat

- Tout utilisateur du tenant TB qui se connecte voit tous les onglets : l'app
  registration « FUSEAU - Dashboard Achats » n'exige aucune affectation
  (`appRoleAssignmentRequired=false`).
- Les lectures de l'API ne contrôlent pas l'identité : seules les écritures
  passent par `require_utilisateur`. Masquer un onglet dans `frontend/index.html`
  ne suffirait donc pas : `/api/previsionnel` resterait lisible en appelant l'URL.
- Les onglets demandés pour Clarisse affichent eux aussi des prix d'achat :
  - **Article** : historique prix (prix en devise et contre-valeur euro) ;
  - **Fiche Achat** : prix unitaire USD.

  Donner ces onglets « sans montants » demande donc de filtrer des champs, pas
  seulement de masquer des onglets.
- La Fiche Achat n'est **jamais enregistrée** : FUSEAU la calcule à la volée et
  l'exporte en Excel (`/api/fiche-achat/export-excel`, modèle FOR-ACH-03-12).
  Il n'existe aucune trace des fiches déjà produites, donc rien à consulter.

## 2. Droits par onglet : proposition

**Profils** (premier jet, à valider) :

| Profil | Personnes | Onglets | Montants |
|---|---|---|---|
| `achats` | Marlène, Maxence, Antho | tous | oui |
| `supply` | E. Georgeon | Suivi commandes, Conteneurs, Prévisionnel, Fournisseurs | à trancher |
| `design` | Clarisse, Thomas, Jonathan | Artwork, Article, Fiche Achat (consultation) | non |
| `qualite` | Éric, service qualité | Qualité, Artwork, Article | non |
| aucun | tout autre compte du tenant | page « accès non attribué » | — |

**Où porter le profil** : rôles d'application Entra (*app roles*) déclarés sur
l'app registration, puis affectés aux personnes ou aux groupes dans l'application
d'entreprise. Easy Auth transmet ces rôles dans l'en-tête `X-MS-CLIENT-PRINCIPAL`.
- Avantages : pas de table de droits à maintenir dans FUSEAU, gestion standard
  dans Entra, révocation centralisée au départ d'une personne.
- Inconvénient : chaque nouvel utilisateur passe par une affectation dans Entra.
- Alternative : une table `achat.utilisateur_profil` modifiable par Antho.
  Plus souple, mais c'est une source de droits de plus à sécuriser.

**Application** :

- Côté API : une dépendance `require_onglet("previsionnel")` sur chaque route.
  Elle renvoie 403 si le profil ne donne pas accès. Les champs de prix sont
  retirés des réponses si le profil n'a pas les montants.
- Côté interface : `/api/moi` renvoie l'identité, le profil et les onglets. Le
  frontend n'affiche que ceux-là. C'est du confort : la sécurité est portée par l'API.
- Écriture : l'archivage d'un artwork est réservé à Maxence (réponse du 08/10),
  via une permission `artwork.archiver` portée par le même mécanisme.
- Les tests vérifient que chaque route `/api/*` déclare son onglet, pour qu'un
  nouvel endpoint ne reste pas ouvert par oubli.

**Mise en route sans couper l'accès** :

1. Livrer le code en mode « journal seul » : l'API journalise les accès qui
   seraient refusés, sans rien bloquer.
2. Créer les rôles dans Entra et affecter les personnes. Cette étape modifie la
   configuration Azure : confirmation écrite d'Antho requise.
3. Après quelques jours sans refus inattendu dans le journal, activer le blocage
   par un flag de configuration.

## 3. Consultation des fiches achat existantes

Deux sources possibles :

- **A. Fiches produites par FUSEAU à partir de maintenant** : à chaque export,
  enregistrer la fiche dans une table `achat.fiche_achat`. On y garde
  l'identifiant, l'article, le PO, la version, le contenu complet en JSON, et la
  date et l'auteur de création. On peut ensuite rechercher et consulter une
  fiche en lecture seule, ou réexporter exactement le même Excel. Rien n'est
  recalculé : la fiche montre ce qui a été envoyé, même si les données ont bougé
  depuis.
- **B. Fiches historiques** (Excel FOR-ACH-03-12 produits avant FUSEAU) :
  - Où sont-elles rangées (Drive, partage réseau) ?
  - Faut-il les indexer, avec un lien vers le fichier par article et par PO,
    ou les reprendre en base ?

Recommandation : faire A dès que possible, car chaque export non enregistré est
perdu pour la consultation. Pour B, se limiter à un index avec lien, une fois
l'emplacement connu.

La consultation entre dans le profil `design` sans les montants, ce qui rejoint
le §2.

## 4. Décisions à prendre

1. Liste des profils et onglets du §2 : à corriger ou valider. Le profil supply
   voit-il les montants ?
2. Rôles Entra (recommandé) ou table de droits FUSEAU ?
3. Clarisse et les autres profils sans montants : sur l'onglet Article et la
   Fiche Achat, masquer les prix suffit-il ?
4. Fiches achat historiques : où sont-elles, et combien ?
5. Comptes du tenant sans profil : page d'accès refusé, ou lecture d'un
   tableau de bord minimal ?
