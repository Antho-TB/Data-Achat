# =============================================================================
# [IAC] FUSEAU - VARIABLES
# =============================================================================

variable "subscription_shsv" {
  description = "Souscription qui porte l'App Service (services partages prod)."
  type        = string
}

variable "subscription_dtpf" {
  description = "Souscription qui porte le VNet du PostgreSQL prive."
  type        = string
}

variable "subscription_management" {
  description = "Souscription de management (Key Vault, logs, state Terraform)."
  type        = string
}

variable "location" {
  description = "Region Azure. Doit rester celle du PostgreSQL pour eviter la latence inter-region."
  type        = string
  default     = "northeurope"
}

variable "prefix" {
  description = "Prefixe Nubo de la souscription hote."
  type        = string
  default     = "shsv"
}

variable "project_code" {
  description = "Code projet, utilise dans tous les noms de ressources."
  type        = string
  default     = "fuseau"
}

variable "environment" {
  description = "Environnement cible."
  type        = string
  default     = "prod"
}

variable "sku_plan" {
  description = "SKU du plan App Service. B1 suffit pour une dizaine d'utilisateurs internes."
  type        = string
  default     = "B1"
}

variable "python_version" {
  description = "Version Python de la Web App. Doit correspondre au venv du poste metier."
  type        = string
  default     = "3.11"
}

# --- Reseau -----------------------------------------------------------------

variable "vnet_shsv_name" {
  description = "VNet spoke qui heberge le subnet d'integration de la Web App."
  type        = string
  default     = "vnet-shsv-network-prod"
}

variable "vnet_shsv_rg" {
  description = "Groupe de ressources du VNet spoke shsv."
  type        = string
  default     = "rg-shsv-network-prod"
}

variable "subnet_webapp_name" {
  description = <<-EOT
    Subnet existant du spoke shsv delegue a l'App Service. Le /24 du spoke est
    deja decoupe en quatre /26, tous vides : on delegue le dernier et on laisse
    les trois premiers libres pour les futurs projets. Ce subnet doit etre
    importe dans le state avant le premier apply (voir README).
  EOT
  type        = string
  default     = "snet-shsv-network-3-prod"
}

variable "vnet_dtpf_name" {
  description = "VNet spoke qui porte le PostgreSQL flexible server prive."
  type        = string
  default     = "vnet-dtpf-network-prod"
}

variable "vnet_dtpf_rg" {
  description = "Groupe de ressources du VNet spoke dtpf."
  type        = string
  default     = "rg-dtpf-network-prod"
}

variable "creer_peering_dtpf" {
  description = <<-EOT
    Cree le peering direct shsv <-> dtpf. Les deux spokes portent une route
    utilisateur 172.31.0.0/16 vers la passerelle du hub : sans peering direct,
    le trafic vers le PostgreSQL depend du transit par cette passerelle, non
    verifie a ce jour. Avec le peering, la route systeme /24 est plus specifique
    que la route utilisateur /16 et gagne, ce qui rend le chemin deterministe.
  EOT
  type        = bool
  default     = true
}

# --- Base de donnees et secrets --------------------------------------------

variable "key_vault_name" {
  description = "Key Vault qui porte les credentials PostgreSQL (RBAC active)."
  type        = string
  default     = "kv-dtpf-prod"
}

variable "key_vault_rg" {
  description = "Groupe de ressources du Key Vault."
  type        = string
  default     = "rg-dtpf-mgmt-prod"
}

variable "pg_host" {
  description = "FQDN du serveur PostgreSQL. Toujours le FQDN, jamais l'IP (regle azure-tb)."
  type        = string
  default     = "psql-dtpf-psql-prod.postgres.database.azure.com"
}

variable "pg_database" {
  description = "Base de donnees cible."
  type        = string
  default     = "dtpf_sylob_prod"
}

variable "secret_login_pg" {
  description = <<-EOT
    Nom du secret Key Vault portant le login PostgreSQL de l'application.
    Un compte de service dedie est attendu : ne jamais pointer un compte nominal
    pour une application hebergee (regle azure-tb).
  EOT
  type        = string
  default     = "psql-prod-fuseau-api-login"
}

variable "secret_password_pg" {
  description = "Nom du secret Key Vault portant le mot de passe du compte de service."
  type        = string
  default     = "psql-prod-fuseau-api-password"
}

# --- Observabilite ----------------------------------------------------------

variable "log_analytics_name" {
  description = "Puits de logs central TB Groupe."
  type        = string
  default     = "log-platform-logs-prod"
}

variable "log_analytics_rg" {
  description = "Groupe de ressources du puits de logs central."
  type        = string
  default     = "rg-platform-logs-prod"
}

variable "tags" {
  description = "Tags obligatoires (policy de tags active sur le tenant)."
  type        = map(string)
}
variable "depot_github" {
  description = "Depot GitHub autorise a deployer, au format proprietaire/nom. Sert de sujet a la federation d'identite OIDC."
  type        = string
  default     = "Antho-TB/Data-Achat"
}
