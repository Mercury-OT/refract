"""Reference authenticator for the demo application.

The demo has no real login flow. The adapter returns a lightweight session
object so the core can exercise the Authenticator port without introducing
product-specific authentication machinery.
"""
from dataclasses import dataclass, field
from uuid import uuid4

from refracto import ports


@dataclass
class Session:
    user: str = field(repr=False)
    context: dict = field(default_factory=dict, repr=False)


class DemoAuthenticator(ports.Authenticator):
    def identify(self, user: str) -> str:
        return f"demo-account:{user}"

    def session(self, user: str) -> ports.UserSession:
        return ports.UserSession(
            principal_id=self.identify(user), authentication_id=str(uuid4()),
            credentials=Session(user=user),
        )
