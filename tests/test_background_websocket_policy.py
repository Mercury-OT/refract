"""An opt-in background channel has no default targets or new HTTP privileges."""
from dataclasses import FrozenInstanceError

import pytest

from refracto_browser import BackgroundWebSocket, BrowserNetworkPolicy

SECURE = 'https://' + 'example.com'
INSECURE = 'http://' + 'example.com'


@pytest.mark.parametrize('path', [None, False, '', '/', 'socket', '//other/socket', '/socket/',
                                  '/socket/*', '/sock%65t', '/events/../socket', '/socket?key', '/socket#topic'])
def test_socket_path_is_exact_and_canonical(path):
    with pytest.raises(ValueError):
        BackgroundWebSocket(path)


@pytest.mark.parametrize('keys', ['cursor', {'key': True}, (None,), ('',), ('a&b',), ('cursor', 'cursor')])
def test_query_names_are_explicit_and_unique(keys):
    with pytest.raises(ValueError):
        BackgroundWebSocket('/socket', query_keys=keys)


def test_socket_permission_is_owned_and_does_not_create_an_http_endpoint():
    keys = ['cursor']
    endpoint = BackgroundWebSocket('/socket', query_keys=keys)
    endpoints = [endpoint]
    base = SECURE
    policy = BrowserNetworkPolicy(credential_origins=(base,), background_websockets=endpoints)
    keys.clear()
    endpoints.clear()
    assert endpoint.query_keys == ('cursor',) and policy.background_websockets == (endpoint,)
    with pytest.raises(FrozenInstanceError):
        endpoint.path = '/other'
    assert policy.bind(base) == base
    with pytest.raises(ValueError):
        policy.classify(base, base + '/socket', 'Fetch', 'GET', {})
    assert BrowserNetworkPolicy().background_websockets == ()


def test_duplicate_paths_and_implicit_credential_destination_are_rejected():
    endpoint = BackgroundWebSocket('/socket')
    with pytest.raises(ValueError):
        BrowserNetworkPolicy(background_websockets=(endpoint, endpoint))
    with pytest.raises(ValueError):
        BrowserNetworkPolicy(background_websockets=(endpoint,)).bind(SECURE)


def test_cleartext_non_loopback_site_and_tls_verification_override_are_not_allowed():
    endpoint = BackgroundWebSocket('/socket')
    with pytest.raises(ValueError):
        BrowserNetworkPolicy(credential_origins=(INSECURE,), background_websockets=(endpoint,)).bind(INSECURE)
    policy = BrowserNetworkPolicy(credential_origins=(SECURE,), background_websockets=(endpoint,))
    with pytest.raises(ValueError):
        policy.validate_context_options(SECURE, {'ignore_https_errors': True})
