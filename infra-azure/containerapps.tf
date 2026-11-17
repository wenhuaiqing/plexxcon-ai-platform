# One container app, two containers in the same replica: nginx (the only
# ingress: SPA, proxy, security headers) and the FastAPI backend on
# 127.0.0.1:8000. No internal ingress and no second proxy, so a cold start is
# one activation.

resource "azurerm_container_app_environment" "main" {
  count                      = local.own_environment ? 1 : 0
  name                       = "cae-${var.prefix}"
  location                   = azurerm_resource_group.main.location
  resource_group_name        = azurerm_resource_group.main.name
  log_analytics_workspace_id = azurerm_log_analytics_workspace.main[0].id

  lifecycle {
    ignore_changes = [workload_profile]
  }
}

resource "azurerm_container_app" "app" {
  # Named for the deployment, not "app": it may share an environment with others.
  name                         = "app-${var.prefix}"
  container_app_environment_id = local.environment_id
  resource_group_name          = azurerm_resource_group.main.name
  revision_mode                = "Single"

  lifecycle {
    ignore_changes = [workload_profile_name]
  }

  ingress {
    external_enabled = true
    target_port      = 80
    traffic_weight {
      latest_revision = true
      percentage      = 100
    }
  }

  secret {
    name  = "demo-write-token"
    value = random_password.write_token.result
  }
  # A secret cannot be empty, so an unset key is stored as a single space; the
  # app strips it, finds no model, and says so on screen.
  secret {
    name  = "llm-api-key"
    value = var.llm_api_key == "" ? " " : var.llm_api_key
  }

  template {
    min_replicas = var.min_replicas
    # One replica: the demo's state - drafts, decisions, the audit log, rate
    # limits - lives in that replica's working copy of the database.
    max_replicas = 1

    # Warm in business hours, so a reviewer opening the link never waits on a
    # cold start; at zero outside them. Defining any rule replaces the default
    # HTTP rule, so it is declared too: a visit at night still wakes the app.
    dynamic "custom_scale_rule" {
      for_each = var.business_hours.enabled ? [1] : []
      content {
        name             = "business-hours"
        custom_rule_type = "cron"
        metadata = {
          timezone        = var.business_hours.timezone
          start           = var.business_hours.start
          end             = var.business_hours.end
          desiredReplicas = "1"
        }
      }
    }
    http_scale_rule {
      name                = "http"
      concurrent_requests = "10"
    }

    container {
      name   = "frontend"
      image  = "${var.image_repo}/frontend:${var.image_tag}"
      cpu    = 0.25
      memory = "0.5Gi"

      env {
        name  = "BACKEND_UPSTREAM"
        value = "127.0.0.1:8000"
      }
    }

    container {
      name  = "backend"
      image = "${var.image_repo}/backend:${var.image_tag}"
      # The data is small; the build ran in the image, so this only serves it.
      cpu    = 0.5
      memory = "1Gi"

      readiness_probe {
        transport               = "HTTP"
        port                    = 8000
        path                    = "/health"
        interval_seconds        = 5
        timeout                 = 3
        failure_count_threshold = 12
        success_count_threshold = 1
      }

      env {
        name  = "LLM_BASE_URL"
        value = var.llm_base_url
      }
      env {
        name        = "LLM_API_KEY"
        secret_name = "llm-api-key"
      }
      env {
        name  = "LLM_CHAT_MODEL"
        value = var.llm_chat_model
      }
      env {
        name  = "LLM_FALLBACK_MODEL"
        value = var.llm_fallback_model
      }
      env {
        name        = "DEMO_WRITE_TOKEN"
        secret_name = "demo-write-token"
      }
    }
  }
}
