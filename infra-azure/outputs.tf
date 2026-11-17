output "frontend_url" {
  description = "The public URL (managed TLS)."
  value       = "https://${azurerm_container_app.app.ingress[0].fqdn}"
}

output "resource_group" {
  description = "Everything is in here. Delete it to remove the deployment."
  value       = azurerm_resource_group.main.name
}

output "demo_write_token" {
  description = "Unlock writes in a browser: <frontend_url>/?write_token=<this>. Never put this link in an application."
  value       = random_password.write_token.result
  sensitive   = true
}
