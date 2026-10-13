# Prescript Backend

API de Prescript construida con Django, Django REST Framework y SimpleJWT. Este servicio concentra la logica del portal medico: autenticacion, agenda, pacientes, preclinica, catalogos, preferencias de medicamentos y recetas.

El backend mantiene sus datos operativos en PostgreSQL y puede consultar informacion de Interactive Core mediante una segunda conexion de base de datos o servicios HTTP internos.

## Stack

- Python
- Django 5.2
- Django REST Framework
- SimpleJWT
- PostgreSQL
- django-environ
- Docker y Gunicorn para ejecucion en contenedor

## Modulos principales

- `auth`: inicio de sesion, refresh de token, usuario autenticado y activacion de doctores.
- `doctor`: perfil del doctor y preferencias de medicamentos.
- `catalog`: catalogos de medicamentos, medicamentos recomendados y examenes.
- `patients`: gestion de pacientes y signos vitales.
- `preclinic`: captura preclinica por cita o paciente.
- `appointments`: agenda de citas.
- `prescriptions`: creacion y consulta de recetas.
- `services/interactive_core`: integracion con Interactive Core.
- `services/country_scope`: aislamiento por pais y seleccion del workspace activo.

La arquitectura multipais, sus roles y la estrategia de migracion estan
documentados en [`docs/multi-country.md`](docs/multi-country.md).

## Requisitos

- Python 3.11 o superior recomendado.
- PostgreSQL disponible localmente o mediante una URL de conexion.
- Base de datos de Prescript creada, por defecto `prescript_db`.
- Base de datos de Interactive Core disponible si se usa la integracion directa, por defecto `interactivecore_db`.

## Configuracion local

```powershell
cd C:\Users\InteractiveCore\Documents\ProyectosAnaliza\Prescript_Backend
python -m venv env
.\env\Scripts\activate
pip install -r requirements.txt
Copy-Item .env.example .env
```

Edita `.env` con las credenciales reales de PostgreSQL y los origenes permitidos del frontend.

Variables mas importantes:

```env
SECRET_KEY=change-me
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1
CORS_ALLOWED_ORIGINS=http://localhost:5173,http://127.0.0.1:5173,http://localhost:5175,http://127.0.0.1:5175
CSRF_TRUSTED_ORIGINS=http://localhost:5173,http://127.0.0.1:5173,http://localhost:5175,http://127.0.0.1:5175

PRESCRIPT_DB=prescript_db
PRESCRIPT_USER=postgres
PRESCRIPT_PASSWORD=postgres
PRESCRIPT_HOST=localhost
PRESCRIPT_PORT=5432

INTERACTIVE_CORE_DB=interactivecore_db
INTERACTIVE_CORE_USER=postgres
INTERACTIVE_CORE_PASSWORD=postgres
INTERACTIVE_CORE_HOST=localhost
INTERACTIVE_CORE_PORT=5432

INTERACTIVE_CORE_API_BASE_URL=
INTERACTIVE_CORE_API_TOKEN=
PRESCRIPT_TOP_DOCTOR_MIN_SCORE=80
```

Tambien se pueden usar `PRESCRIPT_DATABASE_URL`, `INTERACTIVE_CORE_DATABASE_URL` o `DATABASE_URL` cuando el entorno entrega URLs completas.

## Ejecucion local

```powershell
python manage.py migrate
python manage.py runserver 8001
```

API local:

```text
http://localhost:8001/api/v1/
```

Panel admin:

```text
http://localhost:8001/admin/
```

## Ejecucion con Docker

El contenedor lee `.env` y sobreescribe los hosts de base de datos a `host.docker.internal` para conectarse a PostgreSQL instalado en Windows.

```powershell
cd C:\Users\InteractiveCore\Documents\ProyectosAnaliza\Prescript_Backend
docker compose up -d --build
```

API en Docker:

```text
http://localhost:8003/api/v1/
```

Ver logs:

```powershell
docker logs prescript_backend
```

## Endpoints

```text
POST   /api/v1/auth/login
POST   /api/v1/auth/doctor/activate
POST   /api/v1/auth/refresh
GET    /api/v1/auth/me

GET    /api/v1/doctor/me
PATCH  /api/v1/doctor/me
GET    /api/v1/doctor/medicine-preferences
POST   /api/v1/doctor/medicine-preferences
GET    /api/v1/doctor/medicine-preferences/<id>
PATCH  /api/v1/doctor/medicine-preferences/<id>
DELETE /api/v1/doctor/medicine-preferences/<id>

GET    /api/v1/catalog/medicines
GET    /api/v1/catalog/medicines/recommended
GET    /api/v1/catalog/exams

GET    /api/v1/patients
POST   /api/v1/patients
GET    /api/v1/patients/<id>
PATCH  /api/v1/patients/<id>
POST   /api/v1/patients/vitals

GET    /api/v1/preclinic/appointments
POST   /api/v1/preclinic/appointments/<appointment_id>/vitals
GET    /api/v1/preclinic/patients
POST   /api/v1/preclinic/patients/<patient_id>/vitals

GET    /api/v1/appointments
POST   /api/v1/appointments
GET    /api/v1/appointments/<id>
PATCH  /api/v1/appointments/<id>

GET    /api/v1/prescriptions
POST   /api/v1/prescriptions
GET    /api/v1/prescriptions/<id>
```

## Comandos utiles

```powershell
python manage.py makemigrations
python manage.py migrate
python manage.py createsuperuser
python manage.py test
```

## Relacion con el frontend

El frontend `prescript_frontend` consume esta API mediante `VITE_API_URL`. En Docker, la URL esperada por defecto es:

```env
VITE_API_URL=http://localhost:8003/api/v1
```
