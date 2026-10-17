"""Projection-local, fixed-principal authentication with explicit replacement."""
from dataclasses import dataclass, field

from refracto.ports import UserSession


class SessionError(ValueError):
    """Safe, value-free authentication protocol diagnostic."""


@dataclass(frozen=True)
class SessionLease:
    user: str | None
    generation: int
    credentials: object = field(repr=False, metadata={"sensitive": True})


class SessionManager:
    def __init__(self, scenario, auth):
        self.scenario = scenario
        self.auth = auth
        self._principals = {}
        self._current = {}
        self._authentication_ids = set()
        self._ready = False

    def preflight(self):
        users = self.scenario.users
        if (type(users) is not list or any(type(u) is not str or not u.strip() for u in users)
                or len(set(users)) != len(users)):
            raise SessionError("invalid declared users")
        for step in self.scenario.steps:
            user = self.scenario.effective_user(step)
            if ((not users and (step.user is not None or step.session is not None))
                    or (users and user not in users)
                    or (len(users) > 1 and step.user is None)
                    or step.session not in (None, "new")):
                raise SessionError("invalid step user or session policy")
        if users and (not callable(getattr(self.auth, "identify", None))
                      or not callable(getattr(self.auth, "session", None))):
            raise SessionError("Authenticator with fixed user identity is required")
        principals = {}
        for user in users:
            try:
                principal = self.auth.identify(user)
            except Exception:
                raise SessionError("Authenticator could not identify a declared user") from None
            if type(principal) is not str or not principal.strip():
                raise SessionError("Authenticator returned an invalid principal identity")
            if principal in principals.values():
                raise SessionError("declared users must identify distinct accounts")
            principals[user] = principal
        self._principals = principals
        self._ready = True

    def current(self, user):
        return self._current.get(user)

    def acquire(self, user, *, new=False):
        if not self._ready:
            raise SessionError("authentication preflight has not completed")
        if user is None:
            if self.scenario.users or new:
                raise SessionError("anonymous authentication cannot replace a session")
            return SessionLease(None, 0, None)
        if user not in self._principals:
            raise SessionError("undeclared user")
        previous = self._current.get(user)
        if previous is not None and not new:
            return previous
        try:
            acquired = self.auth.session(user)
        except Exception:
            raise SessionError("Authenticator could not acquire the requested session") from None
        if not isinstance(acquired, UserSession):
            raise SessionError("Authenticator must return UserSession")
        if (type(acquired.principal_id) is not str
                or acquired.principal_id != self._principals[user]):
            raise SessionError("authentication changed the declared account")
        identity = acquired.authentication_id
        if type(identity) is not str or not identity.strip():
            raise SessionError("Authenticator returned an invalid authentication identity")
        if identity in self._authentication_ids:
            raise SessionError("Authenticator reused an authentication identity")
        self._authentication_ids.add(identity)
        lease = SessionLease(user, 1 if previous is None else previous.generation + 1,
                             acquired.credentials)
        self._current[user] = lease
        return lease
