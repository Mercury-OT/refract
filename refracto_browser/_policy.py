"""Explicit destination roles for the optional native browser transport."""
from dataclasses import dataclass, field
from types import MappingProxyType
from urllib.parse import urlsplit
import re
import ipaddress

_CREDENTIALS = frozenset({'authorization', 'proxy-authorization', 'cookie'})
_RESOURCES = frozenset({'Document', 'Stylesheet', 'Script', 'Image', 'Font', 'Media', 'TextTrack', 'Manifest', 'Other'})


def canonical_origin(url, *, origin_only=False):
    try:
        if type(url) is not str or not url or any(ord(c) < 33 or ord(c) > 126 for c in url):
            raise ValueError()
        parsed = urlsplit(url)
        host = parsed.hostname
        if (parsed.scheme not in {'http', 'https'} or not host or host.endswith('.')
                or parsed.username is not None or parsed.password is not None
                or '\\' in url or (origin_only and (parsed.path or parsed.query or parsed.fragment))):
            raise ValueError()
        if ':' in host:
            host = ipaddress.IPv6Address(host).compressed
        elif (len(host) > 253 or not all(re.fullmatch(r'[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?', label) for label in host.split('.'))):
            raise ValueError()
        port = parsed.port
        if port is not None and not 1 <= port <= 65535:
            raise ValueError()
        host = '[' + host.lower() + ']' if ':' in host else host.lower()
        suffix = '' if port is None or port == (443 if parsed.scheme == 'https' else 80) else ':' + str(port)
        return parsed.scheme + '://' + host + suffix
    except (ValueError, TypeError):
        raise ValueError('browser origin must be an explicit HTTP(S) origin without credentials') from None


def _contains(prefix, path):
    return prefix in {'', '/'} or path == prefix or path.startswith(prefix + '/')


def _prefix(value, *, actual):
    if type(value) is not str or any(c in value for c in '?%#\\'):
        raise ValueError('browser endpoint prefix is invalid')
    if actual:
        if not value.startswith('/') or (value != '/' and value.endswith('/')):
            raise ValueError('actual endpoint prefix must be a canonical absolute path')
        parts = value[1:].split('/') if value != '/' else []
    else:
        if value.startswith('/') or value.endswith('/'):
            raise ValueError('logical endpoint prefix must be a relative path')
        parts = value.split('/') if value else []
    if any(not p or p in {'.', '..'} or any(ord(c) < 33 for c in p) for p in parts):
        raise ValueError('browser endpoint prefix is invalid')
    return value


@dataclass(frozen=True, slots=True)
class ApiEndpoint:
    origin: str
    path_prefix: str
    logical_prefix: str

    def __post_init__(self):
        object.__setattr__(self, 'origin', canonical_origin(self.origin, origin_only=True))
        _prefix(self.path_prefix, actual=True)
        _prefix(self.logical_prefix, actual=False)


@dataclass(frozen=True, slots=True)
class ResourceRoute:
    origin: str
    path_prefix: str

    def __post_init__(self):
        object.__setattr__(self, 'origin', canonical_origin(self.origin, origin_only=True))
        _prefix(self.path_prefix, actual=True)
        if self.path_prefix == '/':
            raise ValueError('browser resource route must identify a bounded path')


@dataclass(frozen=True, slots=True)
class BackgroundWebSocket:
    """One exact path at the page origin. Query keys are optional, never wildcards."""

    path: str
    query_keys: tuple[str, ...] = ()

    def __post_init__(self):
        if (type(self.path) is not str or len(self.path) > 256
                or not re.fullmatch(r'(/[A-Za-z0-9._~-]+)+', self.path)
                or any(p in {'.', '..'} for p in self.path.split('/'))):
            raise ValueError('background WebSocket requires an exact canonical path')
        keys = self.query_keys
        if (type(keys) not in {tuple, list} or len(keys) > 8
                or any(type(k) is not str or not re.fullmatch(r'[A-Za-z0-9_-]{1,32}', k) for k in keys)
                or len(set(keys)) != len(keys)):
            raise ValueError('background WebSocket requires distinct bounded query keys')
        object.__setattr__(self, 'query_keys', tuple(keys))


@dataclass(frozen=True, slots=True)
class BrowserNetworkPolicy:
    api_endpoints: tuple[ApiEndpoint, ...] = ()
    resource_origins: tuple[str, ...] = ()
    credential_origins: tuple[str, ...] = ()
    credential_headers: object = field(default_factory=dict, repr=False)
    resource_routes: tuple[ResourceRoute, ...] = ()
    background_websockets: tuple[BackgroundWebSocket, ...] = ()

    def __post_init__(self):
        if type(self.api_endpoints) not in {tuple, list} or not all(type(e) is ApiEndpoint for e in self.api_endpoints):
            raise ValueError('browser API endpoints must be explicit endpoint entries')
        endpoints = tuple(self.api_endpoints)
        for index, a in enumerate(endpoints):
            for b in endpoints[index + 1:]:
                if (a.origin == b.origin and (_contains(a.path_prefix, b.path_prefix) or _contains(b.path_prefix, a.path_prefix))
                        or _contains(a.logical_prefix, b.logical_prefix) or _contains(b.logical_prefix, a.logical_prefix)):
                    raise ValueError('browser API endpoint ownership overlaps')
        object.__setattr__(self, 'api_endpoints', endpoints)
        if type(self.resource_routes) not in {tuple, list} or not all(type(r) is ResourceRoute for r in self.resource_routes):
            raise ValueError('browser resource routes must be explicit route entries')
        routes = tuple(self.resource_routes)
        for index, route in enumerate(routes):
            for other in (*routes[index + 1:], *endpoints):
                if (route.origin == other.origin and
                        (_contains(route.path_prefix, other.path_prefix) or _contains(other.path_prefix, route.path_prefix))):
                    raise ValueError('browser resource route ownership overlaps')
        object.__setattr__(self, 'resource_routes', routes)
        sockets = self.background_websockets
        if (type(sockets) not in {tuple, list} or len(sockets) > 16
                or any(type(s) is not BackgroundWebSocket for s in sockets)
                or len({s.path for s in sockets}) != len(sockets)):
            raise ValueError('background WebSocket routes must have distinct exact paths')
        object.__setattr__(self, 'background_websockets', tuple(sockets))
        for name in ('resource_origins', 'credential_origins'):
            values = getattr(self, name)
            if type(values) not in {tuple, list, set, frozenset}:
                raise ValueError('browser origin list is invalid')
            origins = tuple(canonical_origin(v, origin_only=True) for v in values)
            if len(origins) != len(set(origins)):
                raise ValueError('browser origin list contains duplicate origins')
            object.__setattr__(self, name, tuple(sorted(origins)))
        if not hasattr(self.credential_headers, 'items'):
            raise ValueError('credential header policy must be a mapping')
        headers = {}
        for name, origins in self.credential_headers.items():
            if (type(name) is not str or name != name.lower() or not re.fullmatch(r"[a-z0-9!#$%&'*+.^_`|~-]+", name)
                    or name in _CREDENTIALS or name.startswith('x-refract-')):
                raise ValueError('additional credential header name is invalid')
            if type(origins) not in {tuple, list, set, frozenset}:
                raise ValueError('credential destinations must be an explicit origin list')
            headers[name] = frozenset(canonical_origin(v, origin_only=True) for v in origins)
        object.__setattr__(self, 'credential_headers', MappingProxyType(headers))

    def bind(self, base_url):
        base = canonical_origin(base_url)
        if self.background_websockets:
            host = urlsplit(base).hostname
            if base not in self.credential_origins:
                raise ValueError('background WebSocket requires explicit page-origin credential permission')
            if base.startswith('http:') and host != 'localhost':
                try:
                    if not ipaddress.ip_address(host).is_loopback:
                        raise ValueError()
                except ValueError:
                    raise ValueError('cleartext background WebSocket requires a loopback page') from None
        if any(route.origin not in {base, *self.resource_origins} for route in self.resource_routes):
            raise ValueError('browser resource route names an unconfigured resource origin')
        connections = {base, *self.resource_origins, *(e.origin for e in self.api_endpoints)}
        if not set(self.credential_origins).issubset(connections) or any(not set(v).issubset(connections) for v in self.credential_headers.values()):
            raise ValueError('credential policy names an unconfigured destination')
        return base

    def validate_context_options(self, base, options):
        if self.background_websockets and options.get('ignore_https_errors'):
            raise ValueError('background WebSocket requires normal certificate validation')
        if any(options.get(name) for name in ('proxy', 'http_credentials', 'client_certificates')):
            raise ValueError('native browser transport does not support proxy or automatic transport authentication')
        connections = {base, *self.resource_origins, *(e.origin for e in self.api_endpoints)}
        for name in options.get('extra_http_headers', {}):
            lower = name.lower()
            permitted = set(self.credential_origins) if lower in _CREDENTIALS else set(self.credential_headers.get(lower, ()))
            if not connections.issubset(permitted):
                raise ValueError('global browser header cannot safely reach every configured destination')

    def classify(self, base, url, resource_type, method, headers):
        origin = canonical_origin(url)
        lowered = {name.lower(): value for name, value in headers.items()}
        for name in lowered:
            if name in _CREDENTIALS and origin not in self.credential_origins:
                raise ValueError('browser credential destination is not authorized')
            if name in self.credential_headers and origin not in self.credential_headers[name]:
                raise ValueError('browser credential destination is not authorized')
            if name.startswith('x-refract-'):
                raise ValueError('native browser transport received a private wire marker')
        endpoints = [e for e in self.api_endpoints if e.origin == origin and _contains(e.path_prefix, urlsplit(url).path)]
        if resource_type in {'Fetch', 'XHR', 'Preflight'} or method == 'OPTIONS':
            if (resource_type in {'Fetch', 'XHR'} and method in {'GET', 'HEAD'}
                    and origin in {base, *self.resource_origins}
                    and any(route.origin == origin and _contains(route.path_prefix, urlsplit(url).path)
                            for route in self.resource_routes)):
                return origin, None
            if len(endpoints) != 1:
                raise ValueError('browser API destination is not configured')
            endpoint = endpoints[0]
            actual_path = urlsplit(url).path
            suffix = actual_path[1:] if endpoint.path_prefix == '/' else actual_path[len(endpoint.path_prefix):]
            if endpoint.path_prefix != '/' and suffix.startswith('/'):
                suffix = suffix[1:]
            if suffix and any(part in {'', '.', '..'} for part in suffix.split('/')):
                raise ValueError('browser path cannot be silently normalized')
            logical = '/'.join(p for p in (endpoint.logical_prefix, suffix) if p)
            if not logical:
                raise ValueError('browser logical path is empty')
            return origin, logical
        if resource_type not in _RESOURCES or method not in {'GET', 'HEAD'} or origin not in {base, *self.resource_origins}:
            raise ValueError('browser resource destination or transport is not configured')
        return origin, None
