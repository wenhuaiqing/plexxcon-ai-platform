# Azure deployment for the Plexxcon AI operations platform demo.
#
# As small as it can be, on purpose. The data is built inside the image and
# verified against pinned digests, so there is no database server, no storage
# account and no warehouse. The images are public on GitHub Container
# Registry, so there is no registry and no identity to pull with. Secrets are
# Container Apps secrets, so there is no vault. What remains:
#
#   - one resource group, holding everything: deleting it removes the lot
#   - Container Apps, consumption plan, scale to zero (the monthly free grant
#     covers idle and a demo's traffic)
#   - a Log Analytics workspace with a daily cap well inside the free allowance
#   - a monthly budget alert on the resource group
#
# State is local: one operator, one portfolio deployment.

terraform {
  required_version = ">= 1.7"

  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 4.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
  }
}

provider "azurerm" {
  features {}
  subscription_id = var.subscription_id
}
