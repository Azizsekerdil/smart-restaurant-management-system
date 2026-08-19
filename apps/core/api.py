"""DRF ortak bileşenleri: sayfalama ve kullanıcı dostu hata yanıtları."""

from __future__ import annotations

import logging

from django.core.exceptions import PermissionDenied
from django.core.exceptions import ValidationError as DjangoValidationError
from django.http import Http404
from rest_framework import status
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework.views import exception_handler

logger = logging.getLogger("apps.api")


class StandardPagination(PageNumberPagination):
    page_size = 25
    page_size_query_param = "page_size"
    max_page_size = 200

    def get_paginated_response(self, data):
        return Response(
            {
                "count": self.page.paginator.count,
                "page": self.page.number,
                "pages": self.page.paginator.num_pages,
                "page_size": self.get_page_size(self.request),
                "next": self.get_next_link(),
                "previous": self.get_previous_link(),
                "results": data,
            }
        )


# Teknik hata metinlerini kullanıcıya anlaşılır Türkçe karşılıklarıyla verir.
_FRIENDLY = {
    status.HTTP_400_BAD_REQUEST: "Gönderilen bilgilerde hata var. Lütfen alanları kontrol edin.",
    status.HTTP_401_UNAUTHORIZED: "Bu işlem için giriş yapmalısınız.",
    status.HTTP_403_FORBIDDEN: "Bu işlem için yetkiniz bulunmuyor.",
    status.HTTP_404_NOT_FOUND: "Aradığınız kayıt bulunamadı.",
    status.HTTP_405_METHOD_NOT_ALLOWED: "Bu işlem bu adres için desteklenmiyor.",
    status.HTTP_409_CONFLICT: "İşlem mevcut durumla çakışıyor.",
    status.HTTP_429_TOO_MANY_REQUESTS: "Çok fazla istek gönderdiniz. Lütfen biraz bekleyin.",
    status.HTTP_500_INTERNAL_SERVER_ERROR: "Beklenmeyen bir hata oluştu. Yöneticiye bildirildi.",
}


def friendly_exception_handler(exc, context):
    if isinstance(exc, DjangoValidationError):
        return Response(
            {
                "detail": "Doğrulama hatası.",
                "errors": getattr(exc, "message_dict", {"__all__": list(exc.messages)}),
                "code": "validation_error",
            },
            status=status.HTTP_400_BAD_REQUEST,
        )
    if isinstance(exc, PermissionDenied):
        return Response(
            {"detail": _FRIENDLY[status.HTTP_403_FORBIDDEN], "code": "permission_denied"},
            status=status.HTTP_403_FORBIDDEN,
        )
    if isinstance(exc, Http404):
        return Response(
            {"detail": _FRIENDLY[status.HTTP_404_NOT_FOUND], "code": "not_found"},
            status=status.HTTP_404_NOT_FOUND,
        )

    response = exception_handler(exc, context)
    if response is None:
        logger.exception("İşlenmeyen API hatası", exc_info=exc)
        return Response(
            {
                "detail": _FRIENDLY[status.HTTP_500_INTERNAL_SERVER_ERROR],
                "code": "server_error",
            },
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    friendly = _FRIENDLY.get(response.status_code)
    if friendly and isinstance(response.data, dict):
        response.data.setdefault("hint", friendly)
    return response
