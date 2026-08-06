from django.contrib import admin

from api.models import (
    Appointment,
    DoctorAccessLog,
    DoctorCredential,
    DoctorMedicinePreference,
    DoctorPortalProfile,
    ExamCatalogMirror,
    MedicineCatalogMirror,
    Patient,
    PatientMedicalProfile,
    PatientScore,
    PatientVitals,
    Prescription,
    PrescriptionItem,
    NursePortalProfile,
    SecretaryPortalProfile,
)


admin.site.register(DoctorPortalProfile)
admin.site.register(SecretaryPortalProfile)
admin.site.register(NursePortalProfile)
admin.site.register(DoctorCredential)
admin.site.register(DoctorAccessLog)
admin.site.register(Patient)
admin.site.register(PatientMedicalProfile)
admin.site.register(PatientScore)
admin.site.register(PatientVitals)
admin.site.register(Appointment)
admin.site.register(MedicineCatalogMirror)
admin.site.register(DoctorMedicinePreference)
admin.site.register(ExamCatalogMirror)
admin.site.register(Prescription)
admin.site.register(PrescriptionItem)
