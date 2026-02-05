output "app_name" {
  value = juju_application.jupyter_ui.name
}

output "provides" {
  value = {
    provide_cmr_mesh = "provide-cmr-mesh"
  }
}

output "requires" {
  value = {
    dashboard_links     = "dashboard-links",
    ingress             = "ingress",
    istio_ingress_route = "istio-ingress-route",
    logging             = "logging",
    require_cmr_mesh    = "require-cmr-mesh",
    service_mesh        = "service-mesh"
  }
}
