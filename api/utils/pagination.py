from rest_framework.pagination import PageNumberPagination


class OptionalPageNumberPagination(PageNumberPagination):
    """
    Paginacion de 10 en 10 que solo se activa cuando el cliente la pide
    (`?page=` o `?page_size=`). Sin esos parametros la respuesta sigue siendo
    la lista completa: varios selects y pantallas cargan estos mismos endpoints
    para armar opciones y necesitan todos los registros.
    """

    page_size = 10
    page_size_query_param = "page_size"
    max_page_size = 100

    def paginate_queryset(self, queryset, request, view=None):
        params = request.query_params
        if self.page_query_param not in params and self.page_size_query_param not in params:
            return None
        return super().paginate_queryset(queryset, request, view=view)
