"""System trust (including Windows ROOT/CA stores) plus optional corporate CAs."""
import os
import ssl


def client_ssl_context() -> ssl.SSLContext:
    context = ssl.create_default_context()
    bundle = os.environ.get('ARCH_REGISTRY_CA_BUNDLE', '').strip()
    if bundle:
        try:
            context.load_verify_locations(cafile=bundle)
        except (OSError, ssl.SSLError):
            raise ValueError(
                'ARCH_REGISTRY_CA_BUNDLE: не удалось загрузить сертификаты CA. '
                'Укажите существующий PEM-файл с сертификатами корпоративных CA.'
            ) from None
    return context
