from django.urls import include, path


# El contrato publico se conserva bajo /api/v1. Cada modulo de rutas agrupa un
# dominio funcional y evita que este archivo vuelva a concentrar toda la API.
urlpatterns = [
    path("", include("api.routes.system")),
    path("", include("api.routes.auth")),
    path("", include("api.routes.organizations")),
    path("", include("api.routes.theme")),
    path("", include("api.routes.administration")),
    path("", include("api.routes.clinical")),
]
