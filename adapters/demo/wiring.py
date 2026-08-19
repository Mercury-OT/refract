"""Compose the reference demo adapters into a `refracto.runner.Adapters` value."""
from refracto import runner
from refracto.recorder import InMemoryRecorder
from adapters.demo.api import DemoApiDriver
from adapters.demo.auth import DemoAuthenticator
from adapters.demo.config import DemoConfig
from adapters.demo.normalizer import DemoResponseNormalizer
from adapters.demo.resolver import DemoResolver
from adapters.demo.state import DemoStateProbe


def build_adapters(base_url: str, ui=None, scenario=None) -> runner.Adapters:
    config = DemoConfig(base_url=base_url)
    auth = DemoAuthenticator()
    resolver = DemoResolver(config)
    # Some scenarios declare adapter-honoured inputs (e.g. `existing_items: N`) that must
    # take effect at precondition time, before core hands the resolver any scenario. When
    # the caller has the loaded scenario, prime the resolver up front. Absent, resolver
    # defaults apply and every pre-existing scenario behaves exactly as before.
    if scenario is not None:
        resolver.prime_from_scenario(scenario)
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
