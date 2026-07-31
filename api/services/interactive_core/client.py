import requests
from django.conf import settings


class InteractiveCoreClient:
    def __init__(self):
        self.base_url = settings.INTERACTIVE_CORE_API_BASE_URL.rstrip("/")
        self.token = settings.INTERACTIVE_CORE_API_TOKEN

    def _headers(self):
        headers = {"Accept": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    def get(self, path, params=None):
        if not self.base_url:
            raise RuntimeError("INTERACTIVE_CORE_API_BASE_URL no esta configurado.")
        response = requests.get(
            f"{self.base_url}/{path.lstrip('/')}",
            headers=self._headers(),
            params=params,
            timeout=20,
        )
        response.raise_for_status()
        return response.json()

    def patch(self, path, payload):
        if not self.base_url:
            raise RuntimeError("INTERACTIVE_CORE_API_BASE_URL no esta configurado.")
        response = requests.patch(
            f"{self.base_url}/{path.lstrip('/')}",
            headers=self._headers(),
            json=payload,
            timeout=20,
        )
        response.raise_for_status()
        return response.json()
