from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.throttling import ScopedRateThrottle
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from api.serializers.auth_serializers import EmailTokenObtainPairSerializer

LEGACY_ACTIVATION_CLOSED_MESSAGE = (
    "La activacion por identificador ya no esta disponible. "
    "Use el registro de afiliados, que confirma su identidad por correo."
)


class EmailTokenObtainPairView(TokenObtainPairView):
    serializer_class = EmailTokenObtainPairSerializer
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "login"


class ThrottledTokenRefreshView(TokenRefreshView):
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "token_refresh"


class LegacyActivationClosedView(APIView):
    """Reemplaza los endpoints de activacion por identificador (cualquier dato casi publico bastaba).

    Responde 410 sin leer el cuerpo ni consultar Interactive Core, para que un cliente antiguo
    reciba una indicacion clara en lugar de un error confuso.
    """

    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        return Response(
            {"detail": LEGACY_ACTIVATION_CLOSED_MESSAGE, "register_path": "/registro/afiliado"},
            status=status.HTTP_410_GONE,
        )
