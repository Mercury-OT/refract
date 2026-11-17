"""Explicit resource paths cannot grant API evidence or credential permissions."""
from dataclasses import FrozenInstanceError

import pytest

from refracto_browser import ApiEndpoint, BrowserNetworkPolicy, ResourceRoute

BASE = 'https://' + 'example.com'
ASSET = 'https://' + 'example.net'


def policy(*routes, **options):
    return BrowserNetworkPolicy(api_endpoints=(ApiEndpoint(BASE, '/api', 'records'),),
                                resource_routes=routes, **options)


@pytest.mark.parametrize('transport', ['Fetch', 'XHR'])
@pytest.mark.parametrize('method', ['GET', 'HEAD'])
def test_explicit_resource_route_has_no_logical_api_identity(transport, method):
    subject = policy(ResourceRoute(BASE, '/assets'))
    assert subject.bind(BASE) == BASE
    assert subject.classify(BASE, BASE + '/assets/theme.css', transport, method, {}) == (BASE, None)
    assert subject.classify(BASE, BASE + '/api/items', transport, 'GET', {}) == (BASE, 'records/items')
    assert subject.classify(BASE, BASE + '/assets/theme.css', 'Stylesheet', 'GET', {}) == (BASE, None)


@pytest.mark.parametrize('prefix', ['/', '', 'assets', '/assets/', '/assets//css', '/assets/../api', '/assets/%2e', '/assets?x', '/assets#x', False, 2])
def test_resource_route_requires_bounded_canonical_prefix(prefix):
    with pytest.raises(ValueError):
        ResourceRoute(BASE, prefix)


@pytest.mark.parametrize('routes', [
    (ResourceRoute(BASE, '/assets'), ResourceRoute(BASE, '/assets')),
    (ResourceRoute(BASE, '/assets'), ResourceRoute(BASE, '/assets/css')),
    (ResourceRoute(BASE, '/api'),),
    (ResourceRoute(BASE, '/api/files'),),
])
def test_overlapping_resource_or_api_routes_are_rejected(routes):
    with pytest.raises(ValueError):
        policy(*routes)


def test_parent_resource_prefix_cannot_cover_api_mapping():
    with pytest.raises(ValueError):
        BrowserNetworkPolicy(api_endpoints=(ApiEndpoint(BASE, '/assets/api', 'records'),),
                             resource_routes=(ResourceRoute(BASE, '/assets'),))


@pytest.mark.parametrize('routes', [None, {}, 'assets', [None], [{'origin': BASE, 'path_prefix': '/assets'}]])
def test_routes_must_be_explicit_typed_entries(routes):
    with pytest.raises(ValueError):
        BrowserNetworkPolicy(resource_routes=routes)


def test_resource_origin_is_not_authorized_by_route_or_api_permission():
    route = ResourceRoute(ASSET, '/assets')
    with pytest.raises(ValueError):
        policy(route).bind(BASE)
    with pytest.raises(ValueError):
        BrowserNetworkPolicy(api_endpoints=(ApiEndpoint(ASSET, '/api', 'records'),),
                             resource_routes=(route,)).bind(BASE)
    assert policy(route, resource_origins=(ASSET,)).bind(BASE) == BASE


@pytest.mark.parametrize(('transport', 'method'), [('XHR', 'POST'), ('Fetch', 'POST'), ('Preflight', 'OPTIONS'), ('XHR', 'OPTIONS')])
def test_resource_route_never_grants_write_or_preflight(transport, method):
    with pytest.raises(ValueError):
        policy(ResourceRoute(BASE, '/assets')).classify(BASE, BASE + '/assets/data', transport, method, {})


@pytest.mark.parametrize('path', ['/assetss/theme.css', '/other/theme.css'])
def test_resource_route_is_segment_bounded_and_not_a_same_origin_blanket(path):
    with pytest.raises(ValueError):
        policy(ResourceRoute(BASE, '/assets')).classify(BASE, BASE + path, 'XHR', 'GET', {})


@pytest.mark.parametrize('headers', [{'Cookie': 'secret'}, {'Authorization': 'secret'}, {'Proxy-Authorization': 'secret'}, {'X-Refract-marker': 'secret'}])
def test_resource_permission_does_not_bypass_credential_checks(headers):
    with pytest.raises(ValueError):
        policy(ResourceRoute(BASE, '/assets')).classify(BASE, BASE + '/assets/theme.css', 'XHR', 'GET', headers)


def test_additional_credentials_stay_destination_limited():
    subject = policy(ResourceRoute(ASSET, '/assets'), resource_origins=(ASSET,),
                     credential_headers={'x-session': (BASE,)})
    subject.bind(BASE)
    with pytest.raises(ValueError):
        subject.classify(BASE, ASSET + '/assets/theme.css', 'Fetch', 'GET', {'X-Session': 'secret'})


def test_route_and_collection_are_owned_immutable_and_old_positionals_survive():
    route = ResourceRoute(BASE, '/assets')
    with pytest.raises(FrozenInstanceError):
        route.path_prefix = '/other'
    routes = [route]
    subject = BrowserNetworkPolicy((), (), (BASE,), {}, routes)
    routes.clear()
    assert subject.resource_routes == (route,)
    assert subject.classify(BASE, BASE + '/assets/a', 'Fetch', 'GET', {'Cookie': 'allowed'}) == (BASE, None)
    previous = BrowserNetworkPolicy((), (), (BASE,), {})
    assert previous.resource_routes == ()
    with pytest.raises(ValueError):
        previous.classify(BASE, BASE + '/assets/a', 'Fetch', 'GET', {})
