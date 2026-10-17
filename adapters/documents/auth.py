"""Authentication port for the clean-room document target."""

from refracto import ports
from examples.documents.app import DocumentRestApp


class DocumentAuthenticator(ports.Authenticator):
    def __init__(self, app: DocumentRestApp):
        self.app = app

    def identify(self, user: str) -> str:
        return self.app.account_identity(user)

    def session(self, user: str) -> ports.UserSession:
        principal_id, token = self.app.authenticate(user)
        return ports.UserSession(
            principal_id=principal_id, authentication_id=token,
            credentials={"session_key": token},
        )
