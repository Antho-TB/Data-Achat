# =============================================================================
# [IAC] FUSEAU - ENREGISTREMENT D'APPLICATION ENTRA ID
# =============================================================================
# L'authentification de plateforme App Service (Easy Auth) exige un
# enregistrement d'application dans Entra ID. Le projet veille l'avait cree a la
# main et injectait le client_id par le pipeline : ici on le declare, pour que la
# suppression du projet nettoie aussi son identite.
#
# Le secret client est genere par Terraform mais volontairement NON pousse dans
# les app_settings depuis le state : le pipeline le depose dans le Key Vault du
# projet, puis l'app_setting le reference. Voir README, etape 4.
# =============================================================================

data "azuread_client_config" "actuel" {}

resource "azuread_application" "fuseau" {
  display_name     = "FUSEAU - Dashboard Achats"
  owners           = [data.azuread_client_config.actuel.object_id]
  sign_in_audience = "AzureADMyOrg"

  # Identifiant d'application expose, utilise comme audience autorisee.
  identifier_uris = []

  web {
    redirect_uris = [
      "https://app-${var.prefix}-${var.project_code}-${var.environment}.azurewebsites.net/.auth/login/aad/callback",
    ]

    implicit_grant {
      id_token_issuance_enabled = true
    }
  }

  required_resource_access {
    # Microsoft Graph
    resource_app_id = "00000003-0000-0000-c000-000000000000"

    resource_access {
      # User.Read, consentement delegue : suffisant pour identifier l'utilisateur.
      id   = "e1fe6dd8-ba31-4d61-89e7-88639da4683d"
      type = "Scope"
    }
  }
}

resource "azuread_application_password" "fuseau" {
  application_id    = azuread_application.fuseau.id
  display_name      = "easy-auth-app-service"
  end_date_relative = "8760h" # 1 an, a renouveler par le pipeline

  rotate_when_changed = {
    rotation = time_rotating.secret_auth.id
  }
}

# Rotation annuelle automatique du secret d'authentification : un secret qui
# expire sans prevenir coupe l'acces a l'application pour tout le monde.
resource "time_rotating" "secret_auth" {
  rotation_days = 300
}

resource "azuread_service_principal" "fuseau" {
  client_id = azuread_application.fuseau.client_id
  owners    = [data.azuread_client_config.actuel.object_id]
}