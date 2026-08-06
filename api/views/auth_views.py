from rest_framework_simplejwt.views import TokenObtainPairView
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from api.serializers.auth_serializers import (
    DoctorActivationSerializer,
    EmailTokenObtainPairSerializer,
    PortalAccessActivationSerializer,
)


class EmailTokenObtainPairView(TokenObtainPairView):
    serializer_class = EmailTokenObtainPairSerializer


class DoctorActivationView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = DoctorActivationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payload = serializer.save()
        return Response(payload, status=status.HTTP_201_CREATED)


class PortalAccessActivationView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = PortalAccessActivationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payload = serializer.save()
        return Response(payload, status=status.HTTP_201_CREATED)
