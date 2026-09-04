# Valeurs de l'environnement de production. Aucun secret ici : les credentials
# PostgreSQL viennent du Key Vault, le secret Easy Auth est genere par Terraform.

subscription_shsv       = "cef4660c-cb19-43f7-b3f3-c6575a4f836a"
subscription_dtpf       = "d7c0b9c2-62f5-4f9b-96ec-ade07d9e06c7"
subscription_management = "70d5f67e-2e75-416d-a322-457493d18263"

location     = "northeurope"
prefix       = "shsv"
project_code = "fuseau"
environment  = "prod"

tags = {
  project    = "FUSEAU-DataAchat"
  deployment = "IaC"
  owner      = "a.bezille@tb-groupe.fr"
}