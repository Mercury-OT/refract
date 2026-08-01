"""Compose the reference demo adapters into a `refracto.runner.Adapters` value."""
from refracto import runner
from refracto.recorder import InMemoryRecorder
from adapters.demo.api import DemoApiDriver
from adapters.demo.auth import DemoAuthenticator
from adapters.demo.config import DemoConfig
from adapters.demo.normalizer import DemoResponseNormalizer
from adapters.demo.resolver import DemoResolver
from adapters.demo.state import DemoStateProbe


def build_adapters(base_url: str, ui=None) -> runner.Adapters:
    config = DemoConfig(base_url=base_url)
    auth = DemoAuthenticator()
    resolver = DemoResolver(config)
    return runner.Adapters(
        auth=auth,
        api=DemoApiDriver(config),
        state=DemoStateProbe(config),
        ui=ui,
        recorder_factory=InMemoryRecorder,
        resolve_request=resolver.resolve_request,
        resolve_precondition=resolver.resolve_precondition,
        normalizer=DemoResponseNormalizer(),
    )
