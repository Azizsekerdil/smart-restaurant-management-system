"""Yapay zekâ sağlayıcı adapterleri.

Her sağlayıcı `BaseProvider` arayüzünü uygular. Yeni bir sağlayıcı
eklemek için tek yapılması gereken, arayüzü uygulayan bir sınıf yazıp
`registry.PROVIDER_CLASSES` içine kaydetmektir.
"""

from apps.ai.providers.base import (  # noqa: F401
    AIMessage,
    AIResponse,
    BaseProvider,
    ProviderError,
    ProviderNotConfigured,
    ProviderTimeout,
    ProviderUnavailable,
)
from apps.ai.providers.registry import (  # noqa: F401
    available_providers,
    get_provider,
    provider_status,
)
