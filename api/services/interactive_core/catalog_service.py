from .client import InteractiveCoreClient


class InteractiveCoreCatalogService:
    def __init__(self, client=None):
        self.client = client or InteractiveCoreClient()

    def list_medicines(self, params=None):
        return self.client.get("catalog/medicines", params=params)

    def list_exams(self, params=None):
        return self.client.get("catalog/exams", params=params)

    def list_specialties(self, params=None):
        return self.client.get("catalog/specialties", params=params)
