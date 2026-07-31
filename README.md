# Prescript Backend

Backend publico de Prescript construido con Django, Django REST Framework y SimpleJWT, separado de Interactive Core.

## Stack

- Django 5.2
- Django REST Framework
- SimpleJWT
- PostgreSQL local para Prescript por variables `PRESCRIPT_*`
- PostgreSQL local para Interactive Core por alias `interactive_core` y variables `INTERACTIVE_CORE_*`
- CORS configurado por entorno

## Arranque local

```powershell
cd C:\Users\InteractiveCore\Documents\ProyectosAnaliza\Prescript_Backend
python -m venv env
.\env\Scripts\activate
pip install -r requirements.txt
Copy-Item .env.example .env
python manage.py migrate
python manage.py runserver 8001
```

## Arranque con Docker

El contenedor usa el `.env` local, pero sobreescribe los hosts de base de datos a `host.docker.internal` para conectarse a PostgreSQL instalado en Windows.

```powershell
cd C:\Users\InteractiveCore\Documents\ProyectosAnaliza\Prescript_Backend
docker compose up --build
```

La API queda disponible en:

```text
http://localhost:8003/api/v1/
```

Antes de levantar Docker, confirma que ambas bases existan y que PostgreSQL acepte conexiones desde Docker:

```text
prescript_db
interactivecore_db
```

## Variables principales

```env
SECRET_KEY=change-me
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1
CORS_ALLOWED_ORIGINS=http://localhost:5173,http://127.0.0.1:5173
CSRF_TRUSTED_ORIGINS=http://localhost:5173,http://127.0.0.1:5173
PRESCRIPT_DATABASE_URL=
PRESCRIPT_DB=prescript_db
PRESCRIPT_USER=postgres
PRESCRIPT_PASSWORD=postgres
PRESCRIPT_HOST=localhost
PRESCRIPT_PORT=5432

INTERACTIVE_CORE_DATABASE_URL=
INTERACTIVE_CORE_DB=interactivecore_db
INTERACTIVE_CORE_USER=postgres
INTERACTIVE_CORE_PASSWORD=postgres
INTERACTIVE_CORE_HOST=localhost
INTERACTIVE_CORE_PORT=5432

DATABASE_URL=
INTERACTIVE_CORE_API_BASE_URL=
INTERACTIVE_CORE_API_TOKEN=

GUNICORN_WORKERS=3
GUNICORN_THREADS=4
GUNICORN_TIMEOUT=120
```

## Endpoints iniciales

```text
POST   /api/v1/auth/login
POST   /api/v1/auth/refresh
GET    /api/v1/doctor/me
PATCH  /api/v1/doctor/me

GET    /api/v1/catalog/medicines
GET    /api/v1/catalog/medicines/recommended
GET    /api/v1/catalog/exams

GET    /api/v1/patients
POST   /api/v1/patients
GET    /api/v1/patients/<id>
PATCH  /api/v1/patients/<id>
POST   /api/v1/patients/vitals

GET    /api/v1/appointments
POST   /api/v1/appointments
GET    /api/v1/appointments/<id>
PATCH  /api/v1/appointments/<id>

GET    /api/v1/prescriptions
POST   /api/v1/prescriptions
GET    /api/v1/prescriptions/<id>
```

## Integracion con Interactive Core

Los servicios viven en:

```text
api/services/interactive_core/
```

La idea es que Prescript nunca consulte Supabase directamente desde el frontend. El backend de Prescript consume endpoints controlados de Interactive Core o SEMI y mantiene espejos locales para catalogos publicos.
