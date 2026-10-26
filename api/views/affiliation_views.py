from django.contrib.auth.password_validation import validate_password
from rest_framework import generics, serializers, status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from api.utils.pagination import OptionalPageNumberPagination
from api.models import AffiliationRequest
from api.permissions import IsPrescriptAdmin
from api.roles import PRESCRIPT_ROLE_DOCTOR
from api.services.affiliation_service import (
    AFFILIATION_ROLES,
    IDENTIFIER_LABELS,
    MODE_VERIFIED,
    AffiliationReviewService,
    AffiliationService,
)
from api.services.country_scope import get_country_scope
from api.services.registration_service import get_current_terms
from api.views.registration_views import _client_ip


class AffiliationRoleField(serializers.ChoiceField):
    """Rol de la ficha de Interactive Core; sin indicarlo se asume doctor."""

    def __init__(self, **kwargs):
        super().__init__(choices=list(AFFILIATION_ROLES), default=PRESCRIPT_ROLE_DOCTOR, **kwargs)


class AffiliationRequestSerializer(serializers.Serializer):
    role = AffiliationRoleField()
    profile_id = serializers.IntegerField(min_value=1)
    # Solo se usa cuando la ficha de Interactive Core no tiene correo (revision manual).
    email = serializers.EmailField(required=False, allow_blank=True)


class AffiliationActivationSerializer(AffiliationRequestSerializer):
    code = serializers.CharField(max_length=10)
    password = serializers.CharField(min_length=8, write_only=True)
    password_confirm = serializers.CharField(min_length=8, write_only=True)
    accept_terms = serializers.BooleanField()
    phone = serializers.CharField(required=False, allow_blank=True, max_length=25)

    def validate(self, attrs):
        if attrs["password"] != attrs["password_confirm"]:
            raise serializers.ValidationError({"password_confirm": "Las contrasenas no coinciden."})
        validate_password(attrs["password"])
        terms = get_current_terms()
        if terms is None:
            raise serializers.ValidationError({"accept_terms": "Los terminos y condiciones aun no estan publicados."})
        if not attrs["accept_terms"]:
            raise serializers.ValidationError({"accept_terms": "Debe aceptar los terminos y condiciones."})
        attrs["terms"] = terms
        return attrs


class AffiliationBaseView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [ScopedRateThrottle]


class AffiliationSearchView(AffiliationBaseView):
    """Combobox: busca doctores de Interactive Core por nombre o colegiacion."""

    throttle_scope = "affiliation_search"

    def get(self, request):
        role = request.query_params.get("role", PRESCRIPT_ROLE_DOCTOR).upper()
        if role not in AFFILIATION_ROLES:
            raise serializers.ValidationError({"role": "Rol no valido."})
        return Response(AffiliationService().search(role, request.query_params.get("q", "")))


class AffiliationRequestCodeView(AffiliationBaseView):
    throttle_scope = "otp"

    def post(self, request):
        serializer = AffiliationRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        result = AffiliationService().request_code(data["role"], data["profile_id"], email=data.get("email"))
        detail = (
            "Enviamos un codigo al correo registrado en Interactive Core."
            if result["mode"] == MODE_VERIFIED
            else "Enviamos un codigo al correo que indico."
        )
        return Response({"detail": detail, **result})


class AffiliationActivateView(AffiliationBaseView):
    throttle_scope = "otp"

    def post(self, request):
        serializer = AffiliationActivationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        payload = AffiliationService().activate(
            data["role"],
            data["profile_id"],
            data["code"],
            data["password"],
            data["terms"],
            ip_address=_client_ip(request),
            email=data.get("email"),
            phone=data.get("phone"),
        )
        return Response(payload, status=status.HTTP_201_CREATED)


# --- Revision de solicitudes (administradores de Interactive Core) -------------------------


class AffiliationReviewSerializer(serializers.ModelSerializer):
    country_code = serializers.CharField(source="country.code", read_only=True, default=None)
    identifier_label = serializers.SerializerMethodField()

    def get_identifier_label(self, obj):
        return IDENTIFIER_LABELS[obj.role]

    class Meta:
        model = AffiliationRequest
        fields = [
            "id",
            "role",
            "interactive_core_id",
            "full_name",
            "identifier",
            "identifier_label",
            "country_code",
            "email",
            "contact_phone",
            "status",
            "created_at",
            "decided_at",
        ]
        read_only_fields = fields


def _scoped_requests(request):
    """Administrador global ve todas; uno por pais, solo las de su pais."""
    queryset = AffiliationRequest.objects.select_related("country")
    return get_country_scope(request).require_valid().filter(queryset, field="country_id")


class AffiliationRequestListView(generics.ListAPIView):
    serializer_class = AffiliationReviewSerializer
    permission_classes = [IsPrescriptAdmin]
    pagination_class = OptionalPageNumberPagination

    def get_queryset(self):
        queryset = _scoped_requests(self.request)
        status_filter = self.request.query_params.get("status")
        if status_filter in {"pending", "approved", "rejected"}:
            queryset = queryset.filter(status=status_filter)
        return queryset.order_by("-created_at")


class AffiliationDecisionView(APIView):
    permission_classes = [IsPrescriptAdmin]
    approve = True

    def post(self, request, pk):
        affiliation_request = generics.get_object_or_404(_scoped_requests(request), pk=pk)
        service = AffiliationReviewService()
        if self.approve:
            decided = service.approve(affiliation_request.pk, request.user)
        else:
            decided = service.reject(affiliation_request.pk, request.user)
        return Response(AffiliationReviewSerializer(decided).data)
