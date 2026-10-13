from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView

from api.views.auth_views import (
    DoctorActivationView,
    EmailTokenObtainPairView,
    PortalAccessActivationView,
    PortalAccessIdentifierValidationView,
)
from api.views.appointment_views import AppointmentDetailView, AppointmentListCreateView, AppointmentPastRescheduleView
from api.views.catalog_views import ExamCatalogListView, MedicineCatalogListView, RecommendedMedicineListView
from api.views.doctor_views import (
    auth_me_view,
    DoctorListView,
    DoctorMeView,
    DoctorMedicinePreferenceDetailView,
    DoctorMedicinePreferenceListCreateView,
)
from api.views.patient_views import PatientDetailView, PatientListCreateView, PatientVitalsListCreateView
from api.views.preclinic_views import (
    preclinic_appointment_list_view,
    preclinic_patient_list_view,
    preclinic_patient_vitals_upsert_view,
    preclinic_vitals_upsert_view,
)
from api.views.prescription_views import PrescriptionDetailView, PrescriptionListCreateView
from api.views.search_views import global_search_view
from api.views.user_views import AdminUserDetailView, AdminUserListCreateView, AdminUserPasswordResetView


urlpatterns = [
    path("auth/login", EmailTokenObtainPairView.as_view(), name="token-obtain-pair"),
    path("auth/access/activate", PortalAccessActivationView.as_view(), name="portal-access-activate"),
    path("auth/access/validate", PortalAccessIdentifierValidationView.as_view(), name="portal-access-validate"),
    path("auth/doctor/activate", DoctorActivationView.as_view(), name="doctor-activate"),
    path("auth/refresh", TokenRefreshView.as_view(), name="token-refresh"),
    path("auth/me", auth_me_view, name="auth-me"),
    path("search", global_search_view, name="global-search"),
    path("admin/users", AdminUserListCreateView.as_view(), name="admin-user-list-create"),
    path("admin/users/<int:pk>", AdminUserDetailView.as_view(), name="admin-user-detail"),
    path("admin/users/<int:pk>/reset-password", AdminUserPasswordResetView.as_view(), name="admin-user-reset-password"),
    path("doctors", DoctorListView.as_view(), name="doctor-list"),
    path("doctor/me", DoctorMeView.as_view(), name="doctor-me"),
    path("doctor/medicine-preferences", DoctorMedicinePreferenceListCreateView.as_view(), name="doctor-medicine-preferences"),
    path("doctor/medicine-preferences/<int:pk>", DoctorMedicinePreferenceDetailView.as_view(), name="doctor-medicine-preference-detail"),
    path("catalog/medicines", MedicineCatalogListView.as_view(), name="medicine-catalog"),
    path("catalog/medicines/recommended", RecommendedMedicineListView.as_view(), name="recommended-medicines"),
    path("catalog/exams", ExamCatalogListView.as_view(), name="exam-catalog"),
    path("patients", PatientListCreateView.as_view(), name="patient-list-create"),
    path("patients/<int:pk>", PatientDetailView.as_view(), name="patient-detail"),
    path("patients/vitals", PatientVitalsListCreateView.as_view(), name="patient-vitals-list-create"),
    path("preclinic/appointments", preclinic_appointment_list_view, name="preclinic-appointments"),
    path("preclinic/appointments/<int:appointment_id>/vitals", preclinic_vitals_upsert_view, name="preclinic-vitals-upsert"),
    path("preclinic/patients", preclinic_patient_list_view, name="preclinic-patients"),
    path("preclinic/patients/<int:patient_id>/vitals", preclinic_patient_vitals_upsert_view, name="preclinic-patient-vitals-upsert"),
    path("appointments", AppointmentListCreateView.as_view(), name="appointment-list-create"),
    path("appointments/<int:pk>", AppointmentDetailView.as_view(), name="appointment-detail"),
    path("appointments/<int:pk>/reschedule", AppointmentPastRescheduleView.as_view(), name="appointment-past-reschedule"),
    path("prescriptions", PrescriptionListCreateView.as_view(), name="prescription-list-create"),
    path("prescriptions/<int:pk>", PrescriptionDetailView.as_view(), name="prescription-detail"),
]
