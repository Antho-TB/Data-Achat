# =============================================================================
# [IAC] FUSEAU - FOURNISSEURS TERRAFORM
# =============================================================================
# Trois souscriptions sont en jeu, comme sur le projet veille :
#   - defaut      : shsv-prod, porte l'App Service qui sert FUSEAU
#   - dtpf        : dtpf-prod, porte le VNet du PostgreSQL prive (peering)
#   - management  : tb-management, porte le Key Vault kv-dtpf-prod, le puits de
#                   logs central et le state Terraform
# Le state est distant (meme storage que veille), cle dediee au projet.
# =============================================================================

terraform {
  required_version = ">= 1.5"

  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 3.117"
    }
    azuread = {
      source  = "hashicorp/azuread"
      version = "~> 2.53"
    }
    time = {
      source  = "hashicorp/time"
      version = "~> 0.11"
    }
  }

  backend "azurerm" {
    resource_group_name  = "rg-platform-terraform-prod"
    storage_account_name = "stplatformtfstatestbprod"
    container_name       = "tfstates"
    key                  = "shsv-fuseau.tfstate"
    subscription_id      = "70d5f67e-2e75-416d-a322-457493d18263"
    # Authentification Entra ID sur le plan de donnees du storage, pas de cle de
    # compte : la cle partagee est un secret de longue duree que personne ne fait
    # tourner, et le compte de stockage du state peut l'avoir desactivee.
    use_azuread_auth = true
  }
}

provider "azurerm" {
  subscription_id = var.subscription_shsv
  features {}
}

provider "azurerm" {
  alias           = "dtpf"
  subscription_id = var.subscription_dtpf
  features {}
}

provider "azurerm" {
  alias           = "management"
  subscription_id = var.subscription_management
  features {}
}

provider "azuread" {}