"""Authentication port for the clean-room document target."""

from refracto import ports


class DocumentAuthenticator(ports.Authenticator):
    def session(self, role: str) -> object:
        return {"session_key": f"role:{role}"}
