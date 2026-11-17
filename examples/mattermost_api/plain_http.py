"""Explicit pytest/HTTP comparator for the approved S2 and S4 obligations.

Run this module as a pytest file only after setting MATTERMOST_PLAIN_CONFIG to an
external JSON file. It shares transport, not Scenario evaluation, with the pilot.
Never import it as an automatic live-test fixture for the repository suite.
"""

from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import time
from uuid import uuid4

import pytest

from examples.mattermost_api.adapters import MattermostHttp, single_header


SCENARIOS = {
    "S2": ("s02_post_create_read.yaml", "72da52675e9acc7527ee3e7c0e7c8d1bcb7ae3c0287ab60745791626820ced3b"),
    "S4": ("s04_nonmember_post_rejected.yaml", "b1be358cc3ad6019e5ebddb0acd5bf691e43cefd930df7a6623575f8a7945e3a"),
}
SHARED_HASH = "70fa12a879834049766ddb6869c7320e7c51c4ca6fa1e57a21f634adcdf9edca"


def source_hashes():
    root = Path(__file__).parent
    return {name: hashlib.sha256((root / name).read_bytes()).hexdigest()
            for name in ("plain_http.py", "adapters.py")}


def strict_equal(left, right):
    """Independent JSON equality: no Boolean/integer or list-order coercion."""
    if type(left) is not type(right):
        return False
    if type(left) is dict:
        return left.keys() == right.keys() and all(
            strict_equal(left[key], right[key]) for key in left)
    if type(left) is list:
        return len(left) == len(right) and all(
            strict_equal(a, b) for a, b in zip(left, right))
    return left == right


class PlainCase:
    """Business assertions below are written directly, not translated at runtime."""

    def __init__(self, config, case_id, repetition):
        self.config = config
        self.case_id = case_id
        self.repetition = repetition
        self.http = MattermostHttp(config["base_url"])
        self.accounts = json.loads(Path(config["accounts"]).read_text())
        self.tokens = {}
        self.checks = []
        self.sessions = []
        self.current_step = "setup"
        self.failed = False
        self.started = time.perf_counter()
        self.started_utc = datetime.now(timezone.utc).isoformat()
        self.run_id = str(uuid4())
        self.output = Path(config["output_dir"]) / (case_id + "-" + self.run_id)
        self.output.mkdir(parents=True, exist_ok=False)

    def check(self, name, ok, *, stop=True):
        self.checks.append({"step": self.current_step, "check": name, "ok": bool(ok)})
        self.failed |= not ok
        if stop:
            assert ok, f"{self.current_step}: {name}"

    def eq(self, fields, field, value, *, stop=True):
        self.check("field_equals:" + field,
                   field in fields and strict_equal(fields[field], value), stop=stop)

    def neq(self, fields, field, value, *, stop=True):
        self.check("field_not_equals:" + field,
                   field in fields and not strict_equal(fields[field], value), stop=stop)

    def status(self, observation, expected, *, stop=True):
        self.check("status_equals", type(observation.status) is int and observation.status == expected,
                   stop=stop)

    def login(self, user):
        if user not in self.tokens:
            account = self.accounts[user]
            response = self.http.exchange(
                "POST", "/api/v4/users/login",
                body={"login_id": account["login_id"], "password": account["password"]},
                sensitive=True)
            if response.status != 200 or type(response.json) is not dict:
                raise RuntimeError("comparison authentication failed")
            if response.json.get("id") != account["id"]:
                raise RuntimeError("comparison authentication identity mismatch")
            token = single_header(response.headers, "Token")
            if not token:
                raise RuntimeError("comparison authentication token missing")
            self.tokens[user] = token
            self.sessions.append({"user": user, "generation": 1})
        return self.tokens[user]

    def send(self, step, user, method, path, *, body=None, query=None):
        self.current_step = step
        return self.http.exchange(method, "/api/v4/" + path, body=body,
                                  query=query, token=self.login(user))

    def prepare(self):
        token = uuid4().hex
        team_name, channel_name = "rf-team-" + token, "rf-channel-" + token
        response = self.send("setup/current_user", "owner", "GET", "users/me")
        self.status(response, 200)
        self.check("has:id", "id" in response.json)
        self.eq(response.json, "roles", "system_user")
        owner_id = response.json["id"]
        response = self.send("setup/create_team", "owner", "POST", "teams", body={
            "name": team_name, "display_name": "Refract review team", "type": "I",
            "allow_open_invite": False})
        self.status(response, 201)
        self.check("has:id", "id" in response.json)
        self.eq(response.json, "name", team_name)
        self.eq(response.json, "type", "I")
        self.eq(response.json, "allow_open_invite", False)
        team_id = response.json["id"]
        response = self.send("setup/create_channel", "owner", "POST", "channels", body={
            "team_id": team_id, "name": channel_name, "display_name": "Review channel", "type": "P"})
        self.status(response, 201)
        self.check("has:id", "id" in response.json)
        self.eq(response.json, "team_id", team_id)
        self.eq(response.json, "name", channel_name)
        self.eq(response.json, "display_name", "Review channel")
        self.eq(response.json, "type", "P")
        self.eq(response.json, "creator_id", owner_id)
        return owner_id, team_id, response.json["id"]

    def create_post(self, step, channel_id, owner_id, message):
        response = self.send(step, "owner", "POST", "posts", body={
            "channel_id": channel_id, "message": message})
        self.status(response, 201)
        self.check("has:id", "id" in response.json)
        self.eq(response.json, "message", message)
        self.eq(response.json, "channel_id", channel_id)
        self.eq(response.json, "user_id", owner_id)
        return response.json["id"]

    def finish(self, execution_error=None):
        final_sources = source_hashes()
        if final_sources != self.config["frozen_sources"]:
            execution_error = "SourceChanged"
        record = {
            "kind": "ordinary_pytest_http", "case": self.case_id, "run_id": self.run_id,
            "version": self.config["version"], "repetition": self.repetition,
            "started_utc": self.started_utc, "elapsed_seconds": time.perf_counter() - self.started,
            "status": "ERROR" if execution_error else ("FAILED" if self.failed else "PASSED"),
            "execution_error_type": execution_error,
            "observed_server_version": self.config["observed_server_version"],
            "server_preflight": self.config["server_preflight"],
            "frozen_sources": self.config["frozen_sources"], "final_sources": final_sources,
            "scenario_sha256": SCENARIOS[self.case_id][1], "checks": self.checks,
            "sessions": self.sessions, "exchanges": deepcopy(self.http.events),
            "limitations": ["Shares mechanical HTTP transport with the Refract pilot.",
                            "Does not use Refract loading, normalization, evaluation or reporting.",
                            "Positive-run cost comparison is descriptive, not a controlled human study."]}
        path = self.output / "result.json"
        self.http.assert_export_safe(record)
        path.write_text(json.dumps(record, indent=2) + "\n")
        path.chmod(0o600)
        (self.output / "result.sha256").write_text(hashlib.sha256(path.read_bytes()).hexdigest() + "\n")
        if execution_error == "SourceChanged":
            raise RuntimeError("comparison source changed during execution")


@pytest.fixture(scope="module")
def comparison_config():
    setting = os.environ.get("MATTERMOST_PLAIN_CONFIG")
    if not setting:
        pytest.skip("explicit external Mattermost comparison configuration required")
    config = json.loads(Path(setting).read_text())
    if config["version"] not in {"11.7.15", "11.11.4"}:
        raise ValueError("comparison version is not one of the reviewed targets")
    config["frozen_sources"] = source_hashes()
    health = MattermostHttp(config["base_url"])
    response = health.exchange("GET", "/api/v4/system/ping")
    observed = single_header(response.headers, "X-Version-Id")
    if response.status != 200 or not (observed == config["version"] or observed.startswith(config["version"] + ".")):
        raise ValueError("actual comparison server differs from the frozen version")
    config["observed_server_version"] = observed
    config["server_preflight"] = deepcopy(health.events)
    return config


@pytest.fixture
def plain_case(request, comparison_config):
    config = comparison_config
    if source_hashes() != config["frozen_sources"]:
        raise ValueError("comparison source changed before execution")
    case_id, repetition = request.param
    scenario_file, digest = SCENARIOS[case_id]
    root = Path(config["scenarios_dir"])
    if hashlib.sha256((root / scenario_file).read_bytes()).hexdigest() != digest:
        raise ValueError("comparison Scenario differs from the approved input")
    if hashlib.sha256((root / "shared/prepare_private_channel.yaml").read_bytes()).hexdigest() != SHARED_HASH:
        raise ValueError("comparison shared setup differs from the approved input")
    case = PlainCase(config, case_id, repetition)
    try:
        yield case
    finally:
        # Each test records its own final exception category, without sensitive text.
        case.finish(getattr(case, "execution_error", None))


@pytest.mark.parametrize("plain_case", [("S2", n) for n in (1, 2, 3)], indirect=True)
def test_s02_post_create_read(plain_case):
    case = plain_case
    try:
        owner, _, channel = case.prepare()
        message = "Review message A"
        post_id = case.create_post("create_post", channel, owner, message)
        response = case.send("read_post", "owner", "GET", "posts/" + post_id)
        case.status(response, 200, stop=False)
        case.eq(response.json, "id", post_id, stop=False)
        case.eq(response.json, "message", message, stop=False)
        case.eq(response.json, "channel_id", channel, stop=False)
        case.eq(response.json, "user_id", owner, stop=False)
        case.eq(response.json, "delete_at", 0, stop=False)
        assert not case.failed, "one or more ordinary HTTP checks failed"
    except AssertionError:
        raise
    except Exception as error:
        case.execution_error = type(error).__name__
        raise


@pytest.mark.parametrize("plain_case", [("S4", n) for n in (1, 2, 3)], indirect=True)
def test_s04_nonmember_post_rejected(plain_case):
    case = plain_case
    try:
        owner, team, channel = case.prepare()
        response = case.send("identify_peer", "peer", "GET", "users/me")
        case.status(response, 200)
        case.check("has:id", "id" in response.json)
        case.neq(response.json, "id", owner)
        case.eq(response.json, "roles", "system_user")
        peer = response.json["id"]
        response = case.send("add_peer_to_team", "owner", "POST", "teams/" + team + "/members",
                             body={"team_id": team, "user_id": peer})
        case.status(response, 201)
        case.eq(response.json, "team_id", team)
        case.eq(response.json, "user_id", peer)
        case.eq(response.json, "delete_at", 0)
        message = "Channel permission review message"
        case.create_post("member_posts", channel, owner, message)
        response = case.send("list_before", "owner", "GET", "channels/" + channel + "/posts",
                             query={"page": "0", "per_page": "100"})
        case.status(response, 200)
        case.check("has:posts", "posts" in response.json)
        case.neq(response.json, "posts", {})
        order = response.json.get("order")
        case.check("collection_length:order:>=1", type(order) is list and len(order) >= 1)
        case.check("collection_length:order:<100", type(order) is list and len(order) < 100)
        before = deepcopy(response.json)
        response = case.send("nonmember_posts", "peer", "POST", "posts", body={
            "channel_id": channel, "message": message})
        case.status(response, 403, stop=False)
        case.eq(response.json, "id", "api.context.permissions.app_error", stop=False)
        response = case.send("list_after", "owner", "GET", "channels/" + channel + "/posts",
                             query={"page": "0", "per_page": "100"})
        case.status(response, 200, stop=False)
        case.eq(response.json, "posts", before["posts"], stop=False)
        case.eq(response.json, "order", before["order"], stop=False)
        assert not case.failed, "one or more ordinary HTTP checks failed"
    except AssertionError:
        raise
    except Exception as error:
        case.execution_error = type(error).__name__
        raise
