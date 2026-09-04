# =============================================================================
# [IAC] FUSEAU - APP SERVICE, RESEAU, SECRETS, LOGS
# =============================================================================
# FUSEAU est une API FastAPI qui sert aussi son frontend statique. Elle ne parle
# qu'au PostgreSQL Azure (schema achat plus public.articles3) : aucun acces au
# DWH Sylob on-premise, ce qui la rend hebergeable en Azure telle quelle.
#
# L'ETL, lui, reste on-premise par nature (classeur IMPORT sur le partage,
# tarrerias_production_dwh on-premise, boite Gmail Achats). Ce Terraform ne
# deploie donc QUE l'application, pas le pipeline.
#
# Le PostgreSQL a publicNetworkAccess desactive et vit dans un subnet delegue du
# spoke dtpf : la Web App doit sortir par le VNet (integration regionale) et
# resoudre la zone privee privatelink.postgres.database.azure.com, deja liee au
# spoke shsv.
# =============================================================================

locals {
  nom_base = "${var.prefix}-${var.project_code}-${var.environment}"
}

data "azurerm_client_config" "actuel" {}

data "azurerm_log_analytics_workspace" "logs_centraux" {
  provider            = azurerm.management
  name                = var.log_analytics_name
  resource_group_name = var.log_analytics_rg
}

data "azurerm_key_vault" "kv" {
  provider            = azurerm.management
  name                = var.key_vault_name
  resource_group_name = var.key_vault_rg
}

data "azurerm_virtual_network" "shsv" {
  name                = var.vnet_shsv_name
  resource_group_name = var.vnet_shsv_rg
}

data "azurerm_virtual_network" "dtpf" {
  provider            = azurerm.dtpf
  name                = var.vnet_dtpf_name
  resource_group_name = var.vnet_dtpf_rg
}

resource "azurerm_resource_group" "rg" {
  name     = "rg-${local.nom_base}"
  location = var.location
  tags     = var.tags
}

# -----------------------------------------------------------------------------
# RESEAU
# -----------------------------------------------------------------------------
# Le subnet existe deja (decoupage Nubo du /24 spoke) et il est vide. On ne le
# cree pas, on lui ajoute la delegation Microsoft.Web/serverFarms exigee par
# l'integration VNet de l'App Service. D'ou l'import obligatoire avant le
# premier apply : sans lui, Terraform tenterait une creation et echouerait sur
# un prefixe deja pris.
resource "azurerm_subnet" "webapp" {
  name                 = var.subnet_webapp_name
  resource_group_name  = var.vnet_shsv_rg
  virtual_network_name = var.vnet_shsv_name
  address_prefixes     = ["172.31.4.192/26"]

  delegation {
    name = "delegation-app-service"
    service_delegation {
      name    = "Microsoft.Web/serverFarms"
      actions = ["Microsoft.Network/virtualNetworks/subnets/action"]
    }
  }

  lifecycle {
    # Le NSG et la route table du subnet sont poses par l'IaC reseau de Nubo.
    # On ne les revendique pas ici pour ne pas se battre avec leur state.
    ignore_changes = [service_endpoints]
  }
}

resource "azurerm_virtual_network_peering" "shsv_vers_dtpf" {
  count                        = var.creer_peering_dtpf ? 1 : 0
  name                         = "peer-${var.vnet_shsv_name}-to-${var.vnet_dtpf_name}"
  resource_group_name          = var.vnet_shsv_rg
  virtual_network_name         = var.vnet_shsv_name
  remote_virtual_network_id    = data.azurerm_virtual_network.dtpf.id
  allow_virtual_network_access = true
  allow_forwarded_traffic      = true
  # Chaque spoke utilise deja la passerelle du hub : on ne change pas ce reglage.
  allow_gateway_transit = false
  use_remote_gateways   = false
}

resource "azurerm_virtual_network_peering" "dtpf_vers_shsv" {
  provider                     = azurerm.dtpf
  count                        = var.creer_peering_dtpf ? 1 : 0
  name                         = "peer-${var.vnet_dtpf_name}-to-${var.vnet_shsv_name}"
  resource_group_name          = var.vnet_dtpf_rg
  virtual_network_name         = var.vnet_dtpf_name
  remote_virtual_network_id    = data.azurerm_virtual_network.shsv.id
  allow_virtual_network_access = true
  allow_forwarded_traffic      = true
  allow_gateway_transit        = false
  use_remote_gateways          = false
}

# -----------------------------------------------------------------------------
# CALCUL
# -----------------------------------------------------------------------------
resource "azurerm_service_plan" "plan" {
  name                = "plan-${local.nom_base}"
  resource_group_name = azurerm_resource_group.rg.name
  location            = azurerm_resource_group.rg.location
  os_type             = "Linux"
  sku_name            = var.sku_plan
  tags                = var.tags
}

resource "azurerm_linux_web_app" "app" {
  name                = "app-${local.nom_base}"
  resource_group_name = azurerm_resource_group.rg.name
  location            = azurerm_service_plan.plan.location
  service_plan_id     = azurerm_service_plan.plan.id

  https_only                    = true
  virtual_network_subnet_id     = azurerm_subnet.webapp.id
  public_network_access_enabled = true

  site_config {
    always_on = true
    # Route tout le trafic sortant par le VNet : sans cela, la Web App sortirait
    # par Internet et ne joindrait jamais le PostgreSQL prive.
    vnet_route_all_enabled = true
    ftps_state             = "Disabled"
    minimum_tls_version    = "1.2"
    http2_enabled          = true

    application_stack {
      python_version = var.python_version
    }

    # Un seul worker gunicorn avec la classe uvicorn : l'API est I/O bound et le
    # plan B1 n'a qu'un coeur. Le timeout large couvre l'export Excel.
    app_command_line = "gunicorn app.main:app --worker-class uvicorn.workers.UvicornWorker --workers 1 --timeout 180 --bind 0.0.0.0:8000"

    health_check_path                 = "/api/health"
    health_check_eviction_time_in_min = 5
  }

  app_settings = {
    # Credentials PostgreSQL : jamais en clair, lus au Key Vault par l'identite
    # managee (Config.KEY_VAULT_NAME declenche ce chemin dans config_manager).
    "KEY_VAULT_NAME"     = var.key_vault_name
    "PG_HOST"            = var.pg_host
    "PG_DB"              = var.pg_database
    "PG_SSLMODE"         = "require"
    "PG_SECRET_LOGIN"    = var.secret_login_pg
    "PG_SECRET_PASSWORD" = var.secret_password_pg

    # Mode hebergé : l'identite vient de l'authentification de plateforme Entra
    # ID, plus de cle applicative. En mode local (poste metier) la variable vaut
    # apikey et la cle X-API-Key reste exigee.
    "AUTH_MODE" = "entra"

    # L'auto-pull git du poste metier n'a aucun sens ici : le code arrive par le
    # pipeline de deploiement.
    "API_AUTO_PULL" = "0"
    "API_RELOAD"    = "0"

    "WEBSITE_TIMEZONE"                    = "Europe/Paris"
    "SCM_DO_BUILD_DURING_DEPLOYMENT"      = "1"
    "PYTHON_ENABLE_GUNICORN_MULTIWORKERS" = "false"
    "WEBSITE_DNS_SERVER"                  = "168.63.129.16"
  }

  identity {
    type = "SystemAssigned"
  }

  # Authentification Microsoft 365 obligatoire : tout visiteur non authentifie
  # est redirige vers le login Entra ID. C'est la seule barriere d'acces
  # (decision du 03/09/2026), les endpoints d'ecriture s'appuient donc sur
  # l'identite injectee par la plateforme et non sur une cle partagee.
  auth_settings_v2 {
    auth_enabled           = true
    require_authentication = true
    unauthenticated_action = "RedirectToLoginPage"
    default_provider       = "azureactivedirectory"
    require_https          = true

    active_directory_v2 {
      client_id                  = azuread_application.fuseau.client_id
      tenant_auth_endpoint       = "https://login.microsoftonline.com/${data.azurerm_client_config.actuel.tenant_id}/v2.0"
      client_secret_setting_name = "MICROSOFT_PROVIDER_AUTHENTICATION_SECRET"
    }

    login {
      token_store_enabled = true
    }

    # La sonde de sante d'App Service n'a pas d'identite : derriere Easy Auth
    # elle recoit une redirection et finirait par declarer l'instance en
    # mauvaise sante. /api/health ne renvoie qu'un etat de connexion a la base,
    # aucune donnee metier, il peut rester anonyme.
    excluded_paths = ["/api/health"]
  }

  lifecycle {
    # Le secret du provider d'authentification est pose hors state (voir auth.tf)
    # pour ne pas ecrire un secret en clair dans le fichier d'etat.
    ignore_changes = [app_settings["MICROSOFT_PROVIDER_AUTHENTICATION_SECRET"]]
  }

  tags = var.tags
}

# -----------------------------------------------------------------------------
# SECRETS ET LOGS
# -----------------------------------------------------------------------------
# Key Vault en mode RBAC : une attribution de role, pas une access policy.
resource "azurerm_role_assignment" "app_lit_les_secrets" {
  provider             = azurerm.management
  scope                = data.azurerm_key_vault.kv.id
  role_definition_name = "Key Vault Secrets User"
  principal_id         = azurerm_linux_web_app.app.identity[0].principal_id
}

resource "azurerm_monitor_diagnostic_setting" "app_diag" {
  name                       = "diag-${azurerm_linux_web_app.app.name}"
  target_resource_id         = azurerm_linux_web_app.app.id
  log_analytics_workspace_id = data.azurerm_log_analytics_workspace.logs_centraux.id

  enabled_log {
    category = "AppServiceHTTPLogs"
  }

  enabled_log {
    category = "AppServiceConsoleLogs"
  }

  enabled_log {
    category = "AppServiceAppLogs"
  }

  metric {
    category = "AllMetrics"
    enabled  = true
  }
}