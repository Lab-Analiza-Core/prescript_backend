from django.urls import path

from api.views.theme_views import EffectiveThemeView, ThemeDetailView, ThemeLogoView, ThemeOptionsView, ThemeOrganizationListView


urlpatterns = [
    path("theme", EffectiveThemeView.as_view(), name="theme-effective"),
    path("admin/theme", ThemeDetailView.as_view(), name="admin-theme"),
    path("admin/theme/logo", ThemeLogoView.as_view(), name="admin-theme-logo"),
    path("admin/theme/options", ThemeOptionsView.as_view(), name="admin-theme-options"),
    path("admin/theme/organizations", ThemeOrganizationListView.as_view(), name="admin-theme-organizations"),
    path("admin/organizations/<int:organization_id>/theme", ThemeDetailView.as_view(), name="admin-organization-theme"),
    path("admin/organizations/<int:organization_id>/theme/logo", ThemeLogoView.as_view(), name="admin-organization-theme-logo"),
]
