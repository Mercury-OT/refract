"""Compose the three-port adapter used by the second-adapter experiment."""

from refracto import runner
from refracto.recorder import InMemoryRecorder

from adapters.documents.api import DocumentApiDriver
from adapters.documents.auth import DocumentAuthenticator
from adapters.documents.normalizer import DocumentResponseNormalizer
from adapters.documents.resolver import resolve_request
from examples.documents.app import DocumentRestApp


def build_adapters(app: DocumentRestApp | None = None) -> runner.Adapters:
    app = app or DocumentRestApp()
    return runner.Adapters(
        auth=DocumentAuthenticator(),
        api=DocumentApiDriver(app),
        state=None,
        ui=None,
        recorder_factory=InMemoryRecorder,
        resolve_request=resolve_request,
        normalizer=DocumentResponseNormalizer(),
    )
