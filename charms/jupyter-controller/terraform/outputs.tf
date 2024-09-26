output "app_name" {
  value = juju_application.jupyter_controller.name
}

output "provides" {
  value = {
    metrics_endpoint  = "metrics-endpoint",
    grafana_dashboard = "grafana-dashboard",
  }
}

output "requires" {
  value = {
    logging = "logging"
  }
}
