# A tripwire, not a cap: Azure budgets only notify. At rest this deployment
# costs nothing, so the budget is reached only by something unplanned, such as
# a replica left warm.
resource "azurerm_consumption_budget_resource_group" "main" {
  name              = "budget-${var.prefix}-monthly"
  resource_group_id = azurerm_resource_group.main.id
  amount            = var.budget_aud
  time_grain        = "Monthly"

  # Azure refuses a monthly budget that starts before the current month.
  time_period {
    start_date = formatdate("YYYY-MM-01'T'00:00:00Z", plantimestamp())
  }

  notification {
    enabled        = true
    threshold      = 80
    operator       = "GreaterThan"
    threshold_type = "Actual"
    contact_emails = [var.budget_alert_email]
  }

  notification {
    enabled        = true
    threshold      = 100
    operator       = "GreaterThan"
    threshold_type = "Forecasted"
    contact_emails = [var.budget_alert_email]
  }

  lifecycle {
    ignore_changes = [time_period]
  }
}
