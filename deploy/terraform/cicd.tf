# =============================================================================
# [IAC] FUSEAU - IDENTITE DE DEPLOIEMENT GITHUB ACTIONS (OIDC)
# =============================================================================
# Identite dediee au pipeline de deploiement, distincte de l'enregistrement
# Easy Auth declare dans auth.tf : le pipeline deploie du code, Easy Auth
# authentifie des utilisateurs. Les melanger reviendrait a donner a un jeton de
# CI les droits d'une identite utilisateur, et a rendre toute rotation risquee.
#
# Federation d'identite plutot que secret client : GitHub echange un jeton
# signe par son propre emetteur contre un jeton Azure. Aucun secret de longue
# duree ne dort dans les secrets du depot, rien n'expire sans prevenir.
# =============================================================================

resource "azuread_application" "cicd" {
  display_name     = "GitHub Actions - FUSEAU (${var.depot_github})"
  owners           = [data.azuread_client_config.actuel.object_id]
  sign_in_audience = "AzureADMyOrg"
}

resource "azuread_service_principal" "cicd" {
  client_id = azuread_application.cicd.client_id
  owners    = [data.azuread_client_config.actuel.object_id]
}

# -----------------------------------------------------------------------------
# Sujet du jeton : le piege de `environment:`
# -----------------------------------------------------------------------------
# Le job `deployer` de .github/workflows/deploy-azure.yml declare
# `environment: production`. Des qu'un job porte un environnement, GitHub place
# dans la revendication `sub` la forme `repo:<depot>:environment:<nom>` et NON
# `repo:<depot>:ref:refs/heads/main`. Une federation posee sur la branche ne
# correspondrait a aucun jeton et l'etape azure/login echouerait avec un message
# d'audience valide mais de sujet inconnu, difficile a diagnostiquer.
#
# Si l'environnement est un jour retire du workflow, c'est CETTE ressource qu'il
# faut corriger, pas les secrets du depot.
# -----------------------------------------------------------------------------
resource "azuread_application_federated_identity_credential" "cicd_environnement" {
  application_id = azuread_application.cicd.id
  display_name   = "github-actions-fuseau-production"
  description    = "Deploiement depuis l'environnement production du depot ${var.depot_github}."
  audiences      = ["api://AzureADTokenExchange"]
  issuer         = "https://token.actions.githubusercontent.com"
  subject        = "repo:${var.depot_github}:environment:production"
}

# -----------------------------------------------------------------------------
# Droits : strictement le deploiement de l'application, rien d'autre.
# -----------------------------------------------------------------------------
# `Website Contributor` porte sur la seule Web App, pas sur le groupe de
# ressources : le pipeline peut publier du code et redemarrer le site, mais il
# ne peut ni toucher au reseau, ni au Key Vault, ni supprimer le plan. Un jeton
# de CI vole ne donne donc pas la main sur l'infrastructure.
resource "azurerm_role_assignment" "cicd_deploie_lapplication" {
  scope                = azurerm_linux_web_app.app.id
  role_definition_name = "Website Contributor"
  principal_id         = azuread_service_principal.cicd.object_id
}
