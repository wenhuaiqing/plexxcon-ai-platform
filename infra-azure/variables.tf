variable "subscription_id" {
  description = "Subscription to deploy into. Named explicitly so a CLI logged into another subscription cannot receive this deployment by default."
  type        = string
}

variable "prefix" {
  description = "Short resource-name prefix (lowercase alphanumerics and hyphens). The resource group is rg-<prefix>."
  type        = string
  default     = "plexxcon-ai"
}

variable "location" {
  description = "Azure region. Must match the shared environment's region when existing_environment_id is set."
  type        = string
  default     = "australiaeast"
}

variable "existing_environment_id" {
  description = <<-EOT
    Resource id of a Container Apps environment to run in, instead of creating one. A subscription
    may allow only two environments in total; when both are taken, the app joins one of them. The
    app, its secrets and its budget stay in this resource group, so deleting the group still removes
    this deployment - but deleting the group that owns the shared environment would stop it too.
    Empty creates a dedicated environment and log workspace here.
  EOT
  type        = string
  default     = ""
}

variable "image_repo" {
  description = "Public image repository prefix: <this>/frontend:<tag> and <this>/backend:<tag>. Public, so the app pulls with no credential."
  type        = string
  default     = "ghcr.io/wenhuaiqing/plexxcon-ai-platform"
}

variable "image_tag" {
  description = "Tag for both images (the short commit SHA)."
  type        = string
  default     = "latest"
}

variable "min_replicas" {
  description = "0 scales to zero when idle and costs nothing, at the price of a cold start of a few seconds. 1 keeps a replica warm and is billed every second once the monthly free grant is used."
  type        = number
  default     = 0
}

variable "budget_alert_email" {
  description = "Where the monthly cost alert goes."
  type        = string
}

variable "business_hours" {
  description = "Keep one replica warm on a schedule (cron, in the timezone given). Outside it the app scales to zero and the working copy of the database goes back to the build."
  type = object({
    enabled  = bool
    timezone = string
    start    = string
    end      = string
  })
  default = {
    enabled  = true
    timezone = "Australia/Brisbane"
    start    = "0 8 * * 1-5"
    end      = "0 18 * * 1-5"
  }
}

variable "budget_aud" {
  description = "Monthly budget for the resource group, in the subscription's currency. A tripwire, not a cap."
  type        = number
  # Warm for business hours is about A$4-8 a month once the free grant is used.
  default = 10
}

variable "llm_base_url" {
  description = "OpenAI-protocol endpoint for the data agent."
  type        = string
  default     = "https://generativelanguage.googleapis.com/v1beta/openai/"
}

variable "llm_api_key" {
  description = "Key for that endpoint. Empty deploys without a model: catalogue questions are answered and the page says so."
  type        = string
  sensitive   = true
  default     = ""
}

variable "llm_chat_model" {
  description = "Model for the agents. A small, fast one: a question is three or four sequential calls."
  type        = string
  default     = "gemini-3.5-flash-lite"
}

variable "llm_fallback_model" {
  description = "Tried once when the primary answers 429 or 5xx."
  type        = string
  default     = "gemini-3.1-flash-lite"
}
