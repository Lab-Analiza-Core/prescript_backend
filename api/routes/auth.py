from django.urls import path

from api.views.affiliation_views import AffiliationActivateView, AffiliationRequestCodeView, AffiliationSearchView
from api.views.auth_views import EmailTokenObtainPairView, LegacyActivationClosedView, ThrottledTokenRefreshView
from api.views.doctor_views import auth_me_view
from api.views.organization_admin_views import PublicCurrentTermsView, PublicDivisionListView, PublicSpecialtyListView
from api.views.registration_views import (
    ExternalRegistrationView,
    InvitationValidationView,
    PatientHistoryRequestView,
    PatientHistoryVerifyView,
    PatientHistoryView,
)


urlpatterns = [
    path("auth/login", EmailTokenObtainPairView.as_view(), name="token-obtain-pair"),
    path("auth/refresh", ThrottledTokenRefreshView.as_view(), name="token-refresh"),
    path("auth/me", auth_me_view, name="auth-me"),
    path("auth/access/activate", LegacyActivationClosedView.as_view(), name="portal-access-activate"),
    path("auth/access/validate", LegacyActivationClosedView.as_view(), name="portal-access-validate"),
    path("auth/doctor/activate", LegacyActivationClosedView.as_view(), name="doctor-activate"),
    path("auth/register", ExternalRegistrationView.as_view(), name="auth-register"),
    path("auth/invitation/validate", InvitationValidationView.as_view(), name="invitation-validate"),
    path("auth/affiliation/search", AffiliationSearchView.as_view(), name="affiliation-search"),
    path("auth/affiliation/request-code", AffiliationRequestCodeView.as_view(), name="affiliation-request-code"),
    path("auth/affiliation/activate", AffiliationActivateView.as_view(), name="affiliation-activate"),
    path("auth/catalog/divisions", PublicDivisionListView.as_view(), name="public-divisions"),
    path("auth/catalog/specialties", PublicSpecialtyListView.as_view(), name="public-specialties"),
    path("auth/terms/current", PublicCurrentTermsView.as_view(), name="public-terms-current"),
    path("patient/history/request", PatientHistoryRequestView.as_view(), name="patient-history-request"),
    path("patient/history/verify", PatientHistoryVerifyView.as_view(), name="patient-history-verify"),
    path("patient/me/history", PatientHistoryView.as_view(), name="patient-me-history"),
]
