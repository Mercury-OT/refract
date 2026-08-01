"""Reference authenticator for the demo application.

The demo has no real login flow. The adapter returns a lightweight session
object so the core can exercise the Authenticator port without introducing
product-specific authentication machinery.
"""
from dataclasses import dataclass, field

from refracto import ports


@dataclass
class Session:
    role: str
    context: dict = field(default_factory=dict)


class DemoAuthenticator(ports.Authenticator):
    def session(self, role: str) -> Session:
        return Session(role=role)
