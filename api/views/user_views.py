from django.contrib.auth import get_user_model
from django.db.models import Q
from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.views import APIView

from api.permissions import IsPrescriptAdmin
from api.serializers.user_serializers import AdminUserSerializer, UserPasswordResetSerializer


class AdminUserListCreateView(generics.ListCreateAPIView):
    serializer_class = AdminUserSerializer
    permission_classes = [IsPrescriptAdmin]

    def get_queryset(self):
        queryset = (
            get_user_model()
            .objects.all()
            .prefetch_related("groups")
            .select_related("doctor_portal_profile", "secretary_portal_profile", "nurse_portal_profile")
            .order_by("first_name", "last_name", "username")
        )
        search = self.request.query_params.get("search", "").strip()
        status_filter = self.request.query_params.get("is_active", "").strip().lower()
        role = self.request.query_params.get("role", "").strip()

        if search:
            queryset = queryset.filter(
                Q(username__icontains=search)
                | Q(email__icontains=search)
                | Q(first_name__icontains=search)
                | Q(last_name__icontains=search)
                | Q(doctor_portal_profile__full_name__icontains=search)
                | Q(secretary_portal_profile__full_name__icontains=search)
                | Q(nurse_portal_profile__full_name__icontains=search)
            )
        if status_filter in {"true", "false"}:
            queryset = queryset.filter(is_active=status_filter == "true")
        if role:
            queryset = queryset.filter(groups__name=role)

        return queryset.distinct()


class AdminUserDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = AdminUserSerializer
    permission_classes = [IsPrescriptAdmin]
    queryset = get_user_model().objects.all().prefetch_related("groups")

    def destroy(self, request, *args, **kwargs):
        user = self.get_object()
        user.is_active = False
        user.save(update_fields=["is_active"])
        return Response(status=status.HTTP_204_NO_CONTENT)


class AdminUserPasswordResetView(APIView):
    permission_classes = [IsPrescriptAdmin]

    def post(self, request, pk):
        user = generics.get_object_or_404(get_user_model(), pk=pk)
        serializer = UserPasswordResetSerializer(data=request.data, context={"user": user})
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response({"detail": "Contrasena actualizada."})
