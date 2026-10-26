from django.urls import path

from api.views.appointment_views import AppointmentDetailView, AppointmentListCreateView, AppointmentPastRescheduleView
from api.views.catalog_views import ExamCatalogListView, MedicineCatalogListView, RecommendedMedicineListView
from api.views.doctor_views import DoctorListView, DoctorMedicinePreferenceDetailView, DoctorMedicinePreferenceListCreateView, DoctorMeView
from api.views.patient_views import PatientDetailView, PatientListCreateView, PatientVitalsListCreateView
from api.views.preclinic_views import (
    preclinic_appointment_list_view,
    preclinic_patient_list_view,
    preclinic_patient_vitals_upsert_view,
    preclinic_vitals_upsert_view,
)
from api.views.prescription_views import PrescriptionDetailView, PrescriptionListCreateView
from api.views.search_views import global_search_view


urlpatterns = [
    path("search", global_search_view, name="global-search"),
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
