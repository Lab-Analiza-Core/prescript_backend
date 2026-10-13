# Alcance multipais de Prescript

Prescript usa el mismo catalogo operativo de paises que Interactive Core y
mantiene una copia local para poder aplicar llaves foraneas, restricciones e
indices dentro de su propia base de datos.

## Paises iniciales

- Costa Rica (`CR`)
- Guatemala (`GT`)
- Honduras (`HN`)
- El Salvador (`SV`)

Cada fila incluye moneda, codigo telefonico, mascaras de identificacion y
telefono, y zona horaria. La activacion de usuarios actualiza estos datos con
la informacion recibida desde Interactive Core.

## Resolucion del alcance

`api/services/country_scope.py` es la unica autoridad para decidir que paises
puede consultar una peticion:

- `ADMIN` sin pais: administrador global. Puede consultar todos los paises o
  seleccionar uno.
- `ADMIN_HN`, `ADMIN_GT`, `ADMIN_SV`, `ADMIN_CR`: administrador limitado al
  pais indicado.
- `COUNTRY_MANAGER` y roles operativos: usan el pais de su acceso o perfil.
- Una seleccion no autorizada responde `403`; nunca abre la consulta.

El frontend envia la seleccion mediante `X-Prescript-Country`. El encabezado
solo modifica el alcance de un administrador global o elige entre paises que
el usuario ya tiene asignados; no concede acceso nuevo.

## Datos protegidos

El alcance se aplica a doctores, pacientes, citas, preclinica, usuarios y
catalogos. Las recetas y preferencias se validan ademas contra el pais del
doctor para impedir referencias cruzadas.

## Despliegue

Ejecutar la migracion antes de desplegar el frontend:

```powershell
python manage.py migrate
```

La migracion `0012_multi_country_foundation` crea los paises, convierte los
campos de texto existentes a llaves foraneas y asigna los datos historicos sin
pais explicito a Honduras.
