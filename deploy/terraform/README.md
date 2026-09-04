# Deploiement FUSEAU sur Azure App Service

Runbook du passage de FUSEAU du poste de Marlene a une Web App Azure
(decision du 03/09/2026, voir `.ai_memory/decisions_log/`).

## Ce qui part en Azure, ce qui reste sur site

| Composant | Cible | Pourquoi |
|---|---|---|
| API FastAPI + frontend | Azure App Service Linux B1 | Ne parle qu'au PostgreSQL Azure (`achat.*`, `public.articles3`). Verifie le 03/09/2026 : aucun appel au DWH on-premise. |
| ETL (`src/scripts/etl`) | Reste on-premise | Lit le classeur IMPORT sur le partage reseau, le DWH Sylob on-premise et la boite Gmail Achats. Aucun de ces trois n'est joignable depuis Azure. |
| Pipeline Gmail | Reste on-premise | Idem. |

Consequence : le ticket TB-APPS-VM garde tout son sens pour l'ETL. Ce
deploiement ne le remplace pas, il debloque l'acces a l'application.

## Architecture reseau

Le PostgreSQL `psql-dtpf-psql-prod` a `publicNetworkAccess = Disabled` et vit
dans `snet-dtpf-network-0-prod` (VNet `vnet-dtpf-network-prod`, 172.31.2.0/24).
La Web App le joint ainsi :

1. integration VNet regionale dans `snet-shsv-network-3-prod` (172.31.4.192/26,
   vide, delegue a `Microsoft.Web/serverFarms`) ;
2. `vnet_route_all_enabled = true` pour que la sortie passe par le VNet ;
3. resolution du FQDN par la zone privee
   `privatelink.postgres.database.azure.com`, deja liee au spoke shsv ;
4. peering direct `vnet-shsv-network-prod` <-> `vnet-dtpf-network-prod`.

Le peering est necessaire parce que les deux spokes portent une route
utilisateur `172.31.0.0/16` vers la passerelle du hub. Le transit spoke a spoke
par cette passerelle n'est pas verifie, alors qu'avec le peering la route
systeme `/24` est plus specifique que la route utilisateur `/16` et gagne : le
chemin devient deterministe. Passer `creer_peering_dtpf = false` pour tester
d'abord le chemin par le hub.

## Prerequis avant le premier apply

1. **Droits sur le state Terraform.** Le backend est le meme storage que le
   projet veille. Etre Owner ne suffit pas, il faut un role de plan de donnees :

   ```powershell
   az role assignment create `
     --assignee a.bezille@tb-groupe.fr `
     --role "Storage Blob Data Contributor" `
     --scope "/subscriptions/70d5f67e-2e75-416d-a322-457493d18263/resourceGroups/rg-platform-terraform-prod/providers/Microsoft.Storage/storageAccounts/stplatformtfstatestbprod"
   ```

2. **Compte de service PostgreSQL.** L'API tournait sous le compte nominal
   d'Antho : inacceptable pour une application hebergee. Creer le role dedie,
   avec un mot de passe genere hors du depot :

   ```powershell
   # Generer, deposer au Key Vault, puis appliquer le script SQL
   az keyvault secret set --vault-name kv-dtpf-prod --name psql-prod-fuseau-api-login    --value dtpf_fuseau_api_prod
   az keyvault secret set --vault-name kv-dtpf-prod --name psql-prod-fuseau-api-password --value "<secret genere>"
   psql "<chaine platform_team>" -v mot_de_passe="'<secret genere>'" -f ../../sql/20260903_role_api_fuseau.sql
   ```

   Le script est idempotent, non destructif, et affiche en fin d'execution la
   liste des tables ou le role peut ecrire, pour relecture.

3. **Import du subnet.** Le subnet existe deja (decoupage Nubo) et il est vide.
   Terraform lui ajoute seulement la delegation App Service, il ne le cree pas :

   ```powershell
   terraform init
   terraform import azurerm_subnet.webapp `
     "/subscriptions/cef4660c-cb19-43f7-b3f3-c6575a4f836a/resourceGroups/rg-shsv-network-prod/providers/Microsoft.Network/virtualNetworks/vnet-shsv-network-prod/subnets/snet-shsv-network-3-prod"
   ```

## Deroule

```powershell
cd deploy/terraform
terraform init
terraform import azurerm_subnet.webapp "<id du subnet>"   # une seule fois
terraform plan -out tfplan                                 # A RELIRE avant apply
terraform apply tfplan
```

Puis deposer le secret Easy Auth dans la Web App (il est genere par Terraform et
volontairement absent des app settings du state) :

```powershell
$secret = terraform output -raw secret_auth_a_deposer
az webapp config appsettings set -g rg-shsv-fuseau-prod -n app-shsv-fuseau-prod `
  --settings MICROSOFT_PROVIDER_AUTHENTICATION_SECRET=$secret
```

Enfin, deployer le code : pousser sur `main` declenche
`.github/workflows/deploy-azure.yml`, ou lancer le workflow a la main.

## Verifications de recette

1. `terraform output url_application` repond en 302 vers le login Microsoft en
   navigation privee (un 200 anonyme serait une faille, pas un succes).
2. Apres connexion M365, l'onglet Article sort les 3 derniers prix : cela prouve
   la traversee reseau vers le PostgreSQL prive et la lecture du Key Vault.
3. Une ecriture (annotation de commande) aboutit : cela prouve que
   `AUTH_MODE=entra` reconnait bien l'identite injectee par la plateforme.
4. Les logs remontent dans `log-platform-logs-prod` (table `AppServiceConsoleLogs`).

## Retour arriere

Le poste de Marlene reste operationnel pendant toute la bascule : rien n'est
supprime cote poste, `run_api.py` continue de fonctionner en `AUTH_MODE=apikey`.
En cas de probleme, on renvoie simplement le metier vers l'URL locale, et
`terraform destroy` sur ce dossier ne touche que les ressources du projet, le
subnet importe restant en place (seule sa delegation disparait).