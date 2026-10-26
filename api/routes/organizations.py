from django.urls import path

from api.views.affiliation_views import AffiliationDecisionView, AffiliationRequestListView
from api.views.organization_admin_views import (
    InvitationDetailView,
    InvitationListCreateView,
    MemberListView,
    MemberStatusView,
    OrgAdminDecisionView,
    OrgAdminRequestListView,
    OrganizationDetailView,
    OrganizationListCreateView,
    SecretaryAssignmentDetailView,
    SecretaryAssignmentListCreateView,
    TermsVersionListCreateView,
)


urlpatterns = [
    path("admin/affiliation-requests", AffiliationRequestListView.as_view(), name="admin-affiliation-requests"),
    path("admin/affiliation-requests/<int:pk>/approve", AffiliationDecisionView.as_view(approve=True), name="admin-affiliation-approve"),
    path("admin/affiliation-requests/<int:pk>/reject", AffiliationDecisionView.as_view(approve=False), name="admin-affiliation-reject"),
    path("admin/organizations", OrganizationListCreateView.as_view(), name="admin-organizations"),
    path("admin/organizations/<int:pk>", OrganizationDetailView.as_view(), name="admin-organization-detail"),
    path("admin/organizations/<int:organization_id>/invitations", InvitationListCreateView.as_view(), name="admin-invitations"),
    path("admin/invitations/<int:pk>", InvitationDetailView.as_view(), name="admin-invitation-detail"),
    path("admin/members", MemberListView.as_view(), name="admin-members"),
    path("admin/members/<int:pk>", MemberStatusView.as_view(), name="admin-member-status"),
    path("admin/secretary-assignments", SecretaryAssignmentListCreateView.as_view(), name="admin-secretary-assignments"),
    path("admin/secretary-assignments/<int:pk>", SecretaryAssignmentDetailView.as_view(), name="admin-secretary-assignment-detail"),
    path("admin/org-admins", OrgAdminRequestListView.as_view(), name="admin-org-admins"),
    path("admin/org-admins/<int:pk>/approve", OrgAdminDecisionView.as_view(approve=True), name="admin-org-admin-approve"),
    path("admin/org-admins/<int:pk>/reject", OrgAdminDecisionView.as_view(approve=False), name="admin-org-admin-reject"),
    path("admin/terms", TermsVersionListCreateView.as_view(), name="admin-terms"),
]
