"""Mechanical transport mapping: no preparation or invented business values."""
import copy
from refracto import ports
from refracto.query import wire_query


class DemoResolver:
    def __init__(self, config=None):
        self._config = config

    def resolve_request(self, action: ports.RequestAction):
        return ports.RequestSpec(action.method, action.path, copy.deepcopy(action.body),
                                 query=wire_query(action.query or {}),
                                 headers=copy.deepcopy(action.headers or {}))
