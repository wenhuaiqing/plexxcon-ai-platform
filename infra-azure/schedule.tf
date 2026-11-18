# Business hours, warm and cheap.
#
# Two consumption Logic Apps, one at the start of the day and one at the end,
# set the container app's min_replicas to 1 and back to 0 (a JSON merge patch
# through ARM, as the app's own managed identity can do nothing else). A
# replica held by the minimum is billed at the idle rate while nobody is using
# it; a replica started by a scale rule would be billed at the active rate.
# Each run costs a fraction of a cent.

locals {
  warm = var.business_hours.enabled ? {
    start = { hour = var.business_hours.start, min_replicas = 1 }
    stop  = { hour = var.business_hours.end, min_replicas = 0 }
  } : {}
}

resource "azurerm_logic_app_workflow" "warm" {
  for_each            = local.warm
  name                = "logic-${var.prefix}-warm-${each.key}"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name

  identity {
    type = "SystemAssigned"
  }
}

# Scoped to this one container app: the schedule can change nothing else.
resource "azurerm_role_assignment" "warm" {
  for_each             = local.warm
  scope                = azurerm_container_app.app.id
  role_definition_name = "Contributor"
  principal_id         = azurerm_logic_app_workflow.warm[each.key].identity[0].principal_id
}

resource "azurerm_logic_app_trigger_recurrence" "warm" {
  for_each     = local.warm
  name         = "weekdays"
  logic_app_id = azurerm_logic_app_workflow.warm[each.key].id
  frequency    = "Week"
  interval     = 1
  time_zone    = var.business_hours.time_zone

  schedule {
    on_these_days    = var.business_hours.days
    at_these_hours   = [each.value.hour]
    at_these_minutes = [0]
  }
}

resource "azurerm_logic_app_action_custom" "warm" {
  for_each     = local.warm
  name         = "set-min-replicas"
  logic_app_id = azurerm_logic_app_workflow.warm[each.key].id

  body = jsonencode({
    type = "Http"
    inputs = {
      method  = "PATCH"
      uri     = "https://management.azure.com${azurerm_container_app.app.id}?api-version=2024-03-01"
      headers = { "Content-Type" = "application/json" }
      body    = { properties = { template = { scale = { minReplicas = each.value.min_replicas } } } }
      authentication = {
        type     = "ManagedServiceIdentity"
        audience = "https://management.azure.com/"
      }
      retryPolicy = { type = "exponential", count = 4, interval = "PT1M" }
    }
    runAfter = {}
  })
}
