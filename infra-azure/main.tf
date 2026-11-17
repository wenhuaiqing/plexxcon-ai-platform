# Everything lives in this one group. `terraform destroy`, or deleting the
# group in the portal, removes the whole deployment and nothing else.
resource "azurerm_resource_group" "main" {
  name     = "rg-${var.prefix}"
  location = var.location

  tags = {
    purpose = "portfolio-demo"
    repo    = "plexxcon-ai-platform"
  }
}

# Container Apps logging. PerGB2018 includes 5 GB a month free per billing
# account; the daily cap keeps this workspace to about 1.5 GB a month at the
# very most, so a logging loop cannot become a bill.
resource "azurerm_log_analytics_workspace" "main" {
  count               = local.own_environment ? 1 : 0
  name                = "log-${var.prefix}"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  sku                 = "PerGB2018"
  retention_in_days   = 30
  daily_quota_gb      = 0.05
}

locals {
  own_environment = var.existing_environment_id == ""
  environment_id  = local.own_environment ? azurerm_container_app_environment.main[0].id : var.existing_environment_id
}

# Every write - drafts, submissions, reviews, confirmed dockets, reset - needs this. The operator opens the site once
# with ?write_token=<value>; the plain link is read-only.
resource "random_password" "write_token" {
  length  = 32
  special = false
}

# No registry: the images are public on GitHub Container Registry
# (var.image_repo). A private registry's cheapest tier costs more each month
# at rest than this whole deployment, and a public image of a public
# repository of synthetic data hides nothing. A public pull needs no
# credential, so none exists to leak.
#
# No vault: the two secrets are Container Apps secrets, encrypted at rest by
# the platform and readable only by this app. A vault earns its place when a
# secret has more than one consumer or needs rotation; neither is true here.
