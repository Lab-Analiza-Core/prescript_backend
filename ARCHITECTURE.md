# Arquitectura del backend

Prescript conserva una sola aplicacion Django (`api`) para mantener estables las
migraciones, los `ContentType`, las relaciones y los permisos existentes.

La organizacion interna sigue estas responsabilidades:

- `api/models`: persistencia separada por dominio.
- `api/serializers`: validacion y representacion de la API.
- `api/services`: reglas de negocio y coordinacion con sistemas externos.
- `api/views`: adaptadores HTTP delgados.
- `api/routes`: rutas agrupadas por dominio (`auth`, `organizations`, `theme`,
  `administration`, `clinical` y `system`).
- `api/permissions`: autorizacion reutilizable.

`api/urls.py` es solamente el punto de composicion. Las rutas publicas bajo
`/api/v1` y sus nombres son un contrato y estan protegidas por
`ApiRouteContractTests`.

Al agregar funcionalidad, la regla es mantener la logica de negocio fuera de
las vistas y registrar la URL en el modulo de dominio correspondiente.
