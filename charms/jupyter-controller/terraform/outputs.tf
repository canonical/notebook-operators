output "app_name" {
  value = juju_application.jupyter_controller.name
}

output "provides" {
  value = {
    grafana_dashboard = "grafana-dashboard",
    metrics_endpoint  = "metrics-endpoint",
    provide_cmr_mesh  = "provide-cmr-mesh"
  }
}

output "requires" {
  value = {
    gateway_metadata = "gateway-metadata",
    logging          = "logging",
    require_cmr_mesh = "require-cmr-mesh",
    service_mesh     = "service-mesh"
  }
}
