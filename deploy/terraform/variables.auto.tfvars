# Valeurs de l'environnement de production. Aucun secret ici : les credentials
# PostgreSQL viennent du Key Vault, le secret Easy Auth est genere par Terraform.

subscription_shsv       = "cef4660c-cb19-43f7-b3f3-c6575a4f836a"
subscription_dtpf       = "d7c0b9c2-62f5-4f9b-96ec-ade07d9e06c7"
subscription_management = "70d5f67e-2e75-416d-a322-457493d18263"

location     = "northeurope"
prefix       = "shsv"
project_code = "fuseau"
environment  = "prod"

# Les policies du management group mg-tb exigent les tags project et deployment.
# Le tag owner est volontairement ABSENT : l'assignation "tag-owner-a" passe une
# expression reguliere a l'operateur notMatch d'Azure Policy, qui utilise une
# syntaxe de motif (# chiffre, ? lettre), pas une regex. Aucune adresse mail ne
# peut donc satisfaire ce motif, et toute ressource portant un tag owner est
# refusee (constate le 03/09/2026 sur la creation du plan App Service). La
# policy ne se declenche que si le tag existe : on ne le pose pas, et le sujet
# est remonte a Nubo pour correction (motif du type ?*@?*.?* ou effet audit).
tags = {
  project    = "FUSEAU-DataAchat"
  deployment = "IaC"
}