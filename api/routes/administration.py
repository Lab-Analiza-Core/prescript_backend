from django.urls import path

from api.views.user_views import AdminUserDetailView, AdminUserListCreateView, AdminUserPasswordResetView


urlpatterns = [
    path("admin/users", AdminUserListCreateView.as_view(), name="admin-user-list-create"),
    path("admin/users/<int:pk>", AdminUserDetailView.as_view(), name="admin-user-detail"),
    path("admin/users/<int:pk>/reset-password", AdminUserPasswordResetView.as_view(), name="admin-user-reset-password"),
]
