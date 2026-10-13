from rest_framework import serializers

from api.models import Country


class CountrySerializer(serializers.ModelSerializer):
    class Meta:
        model = Country
        fields = [
            "id",
            "interactive_core_id",
            "code",
            "name",
            "currency",
            "phone_code",
            "dni_mask",
            "phone_mask",
            "timezone",
        ]
        read_only_fields = fields
