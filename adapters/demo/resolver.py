"""Mechanical transport mapping: no preparation or invented business values."""
import copy
from refracto import ports


class DemoResolver:
    def __init__(self, config=None):
        self._config = config

    def resolve_request(self, scenario, step, template):
        return ports.RequestSpec(template.method, template.path, copy.deepcopy(template.body))
