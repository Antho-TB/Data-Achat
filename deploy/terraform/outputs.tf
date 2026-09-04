# =============================================================================
# [IAC] FUSEAU - SORTIES
# =============================================================================

output "url_application" {
  description = "URL a communiquer au service Achats."
  value       = "https://${azurerm_linux_web_app.app.default_hostname}"
}

output "nom_application" {
  description = "Nom de la Web App, cible du pipeline de deploiement."
  value       = azurerm_linux_web_app.app.name
}

output "identite_application" {
  description = "Principal de l'identite managee, a autoriser cote PostgreSQL si on passe un jour a l'authentification Entra sur la base."
  value       = azurerm_linux_web_app.app.identity[0].principal_id
}

output "client_id_entra" {
  description = "Client id de l'enregistrement d'application Entra ID."
  value       = azuread_application.fuseau.client_id
}

output "secret_auth_a_deposer" {
  description = "Secret d'authentification Easy Auth. A deposer dans l'app_setting MICROSOFT_PROVIDER_AUTHENTICATION_SECRET par le pipeline."
  value       = azuread_application_password.fuseau.value
  sensitive   = true
}

output "peering_actif" {
  description = "Vrai si le peering direct shsv vers dtpf a ete cree."
  value       = var.creer_peering_dtpf
}