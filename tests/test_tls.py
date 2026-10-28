import ssl
import certifi
import httpx

import pytest

from backend.app.tls import client_ssl_context


def test_system_trust_and_verification(monkeypatch):
    monkeypatch.delenv('ARCH_REGISTRY_CA_BUNDLE', raising=False)
    context = client_ssl_context()
    assert context.verify_mode == ssl.CERT_REQUIRED
    assert context.check_hostname
    assert context.cert_store_stats()['x509_ca'] > 0


def test_additional_ca_is_added_to_system_context(monkeypatch, tmp_path):
    bundle = tmp_path / 'corporate CA.pem'
    bundle.write_text('test bundle')
    calls = []

    class Context:
        def load_verify_locations(self, *, cafile):
            calls.append(cafile)

    context = Context()
    monkeypatch.setattr(ssl, 'create_default_context', lambda: context)
    monkeypatch.setenv('ARCH_REGISTRY_CA_BUNDLE', str(bundle))
    assert client_ssl_context() is context
    assert calls == [str(bundle)]


@pytest.mark.parametrize('contents', [None, 'not a certificate'])
def test_invalid_ca_fails_closed(monkeypatch, tmp_path, contents):
    bundle = tmp_path / 'invalid.pem'
    if contents is not None:
        bundle.write_text(contents)
    monkeypatch.setenv('ARCH_REGISTRY_CA_BUNDLE', str(bundle))
    with pytest.raises(ValueError, match='ARCH_REGISTRY_CA_BUNDLE'):
        client_ssl_context()


def test_real_pem_bundle_keeps_verification(monkeypatch):
    monkeypatch.setenv('ARCH_REGISTRY_CA_BUNDLE', certifi.where())
    context = client_ssl_context()
    assert context.verify_mode == ssl.CERT_REQUIRED
    assert context.check_hostname
    assert context.cert_store_stats()['x509_ca'] > 0


def test_both_integrations_pass_explicit_system_context(monkeypatch):
    from backend.app.confluence.client import ConfluenceClient
    from backend.app.providers import OpenAICompatible

    monkeypatch.delenv('ARCH_REGISTRY_CA_BUNDLE', raising=False)
    original = httpx.Client
    contexts = []

    def capture(*args, **kwargs):
        contexts.append(kwargs['verify'])
        return original(*args, **kwargs)

    monkeypatch.setattr(httpx, 'Client', capture)
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json={'data': []}))
    with ConfluenceClient('https://wiki.example', 'test', transport=transport):
        pass
    OpenAICompatible({'base_url': 'https://llm.example/v1'}, transport=transport).models()
    assert len(contexts) == 2
    assert all(c.check_hostname and c.verify_mode == ssl.CERT_REQUIRED for c in contexts)
