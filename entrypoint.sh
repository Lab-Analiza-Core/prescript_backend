#!/usr/bin/env bash
set -e

export DJANGO_SETTINGS_MODULE="${DJANGO_SETTINGS_MODULE:-Prescript.settings}"
WSGI_MODULE="${WSGI_MODULE:-Prescript.wsgi}"

echo "$(date +'%F %T') | Esperando bases de datos..."
until python - <<'PY'
import os

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "Prescript.settings")
django.setup()

from django.db import connections

aliases = ["default"]
if os.environ.get("REQUIRE_INTERACTIVE_CORE_ON_STARTUP", "false").lower() in {"1", "true", "yes"}:
    aliases.append("interactive_core")
for alias in aliases:
    connections[alias].ensure_connection()
    print(f"{alias}=OK")
PY
do
    echo "$(date +'%F %T') | BD no disponible, reintentando en 3s..."
    sleep 3
done

echo "$(date +'%F %T') | Aplicando migraciones en prescript_db..."
python manage.py migrate --noinput

echo "$(date +'%F %T') | Collectstatic..."
python manage.py collectstatic --noinput --clear

echo "$(date +'%F %T') | Iniciando Gunicorn..."
exec gunicorn "${WSGI_MODULE}:application" \
  --bind 0.0.0.0:8000 \
  --workers "${GUNICORN_WORKERS:-3}" \
  --worker-class gthread \
  --threads "${GUNICORN_THREADS:-4}" \
  --timeout "${GUNICORN_TIMEOUT:-120}"
