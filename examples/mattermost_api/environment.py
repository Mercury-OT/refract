"""Dedicated loopback-only pilot environment; never manages unrelated resources.

All generated credentials, configuration and logs belong in an explicit external
directory. This host utility is separate from business Scenario execution.
"""

import argparse
import datetime as dt
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import time
import urllib.error
import urllib.request


IMAGES = {
    "11.7.15": "mattermost/mattermost-team-edition@sha256:c2f5c857ba6386bc62051daf80fe127995fa23ea769359bc14cde183f7bbf595",
    "11.11.4": "mattermost/mattermost-team-edition@sha256:6dea23955b75fe17f181faa9803bb351da32438c71c594026d3d500b2eaed749",
}
DATABASE_IMAGE = "postgres@sha256:95206741a5b214807675e14165369d05b93a9cf692223b616d07cca227e74b0b"
LABEL = "refract.mattermost-pilot"


def write_private(path, value):
    path = Path(path)
    with path.open("w", encoding="utf-8") as stream:
        os.chmod(path, 0o600)
        json.dump(value, stream, indent=2)
        stream.write("\n")


def stamp():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def command(root, *args, timeout=120):
    started, tick = stamp(), time.monotonic()
    result = subprocess.run(["docker", *args], capture_output=True, text=True,
                            timeout=timeout)
    row = {"started_utc": started, "elapsed_seconds": time.monotonic() - tick,
           "command": ["docker", *args], "exit_code": result.returncode}
    # Arguments contain file references, never passwords or account tokens.
    with (root / "commands.jsonl").open("a", encoding="utf-8") as stream:
        os.chmod(root / "commands.jsonl", 0o600)
        stream.write(json.dumps(row) + "\n")
    if result.returncode:
        (root / "last-command-error.txt").write_text(result.stderr)
        os.chmod(root / "last-command-error.txt", 0o600)
        raise RuntimeError("environment command failed; inspect external diagnostics")
    return result.stdout.strip()


def api(base, method, path, body=None):
    data = None if body is None else json.dumps(body).encode()
    request = urllib.request.Request(base + "/api/v4" + path, data=data,
                                     method=method,
                                     headers={"Content-Type": "application/json"})
    # Host setup is only used at the locally created origin.
    with urllib.request.urlopen(request, timeout=15) as response:
        return response.status, json.load(response), dict(response.headers)


def wait_ready(root, state, timeout=300):
    started, tick = stamp(), time.monotonic()
    attempts = 0
    while time.monotonic() - tick < timeout:
        attempts += 1
        try:
            status, body, headers = api(state["base_url"], "GET", "/system/ping")
            if status == 200 and body.get("status") == "OK":
                row = {"started_utc": started, "elapsed_seconds": time.monotonic()-tick,
                       "attempts": attempts, "status": status,
                       "body": body, "server_version": headers.get("X-Version")}
                write_private(root / ("ready-" + state["version"] + ".json"), row)
                return
        except (OSError, ValueError, urllib.error.URLError):
            pass
        time.sleep(1)
    capture_logs(root, state)
    raise RuntimeError("Mattermost did not become ready within the host budget")


def capture_logs(root, state):
    for key in ("app", "database"):
        result = subprocess.run(["docker", "logs", state[key]], capture_output=True,
                                text=True, timeout=30)
        path = root / (key + "-" + state["version"] + ".log")
        path.write_text(result.stdout + result.stderr)
        os.chmod(path, 0o600)


def run_app(root, state):
    command(root, "run", "-d", "--name", state["app"], "--label", LABEL,
            "--platform", "linux/amd64", "--network", state["network"],
            "--memory", "3g", "--cpus", "3", "--env-file", str(root / "app.env"),
            "-p", "127.0.0.1:" + str(state["port"]) + ":8065",
            IMAGES[state["version"]])
    write_private(root / "state.json", state)
    wait_ready(root, state)


def start(root):
    if (root / "state.json").exists():
        raise RuntimeError("refusing to overwrite an existing environment")
    prefix = "rf-mm-pilot-" + secrets.token_hex(4)
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    state = {"prefix": prefix, "network": prefix + "-net",
             "database": prefix + "-db", "volume": prefix + "-data",
             "app": prefix + "-app-a", "port": port,
             "base_url": "http://127.0.0.1:" + str(port),
             "version": "11.7.15", "created_utc": stamp()}
    password = secrets.token_hex(24)
    database_env = {"POSTGRES_USER": "pilot", "POSTGRES_PASSWORD": password,
                    "POSTGRES_DB": "mattermost"}
    app_env = {
        "MM_SQLSETTINGS_DRIVERNAME": "postgres",
        "MM_SQLSETTINGS_DATASOURCE": "postgres://pilot:" + password + "@" + state["database"] + ":5432/mattermost?sslmode=disable&connect_timeout=10",
        "MM_SERVICESETTINGS_SITEURL": state["base_url"],
        "MM_TEAMSETTINGS_ENABLEOPENSERVER": "true",
        "MM_EMAILSETTINGS_REQUIREEMAILVERIFICATION": "false",
        "MM_EMAILSETTINGS_SENDEMAILNOTIFICATIONS": "false",
        "MM_PLUGINSETTINGS_ENABLE": "false",
        "MM_LOGSETTINGS_ENABLEDIAGNOSTICS": "false",
        "MM_LOGSETTINGS_ENABLEFILE": "false",
        "MM_LOGSETTINGS_CONSOLELEVEL": "WARN",
    }
    for name, env in (("database.env", database_env), ("app.env", app_env)):
        path = root / name
        path.write_text("".join(key + "=" + value + "\n" for key, value in env.items()))
        os.chmod(path, 0o600)
    write_private(root / "state.json", state)
    command(root, "network", "create", "--label", LABEL, state["network"])
    command(root, "volume", "create", "--label", LABEL, state["volume"])
    command(root, "run", "-d", "--name", state["database"], "--label", LABEL,
            "--platform", "linux/arm64", "--network", state["network"],
            "--memory", "768m", "--env-file", str(root / "database.env"),
            "-v", state["volume"] + ":/var/lib/postgresql/data", DATABASE_IMAGE)
    for _ in range(60):
        probe = subprocess.run(["docker", "exec", state["database"], "pg_isready", "-U", "pilot", "-d", "mattermost"], capture_output=True)
        if probe.returncode == 0:
            break
        time.sleep(1)
    else:
        raise RuntimeError("dedicated database readiness failed")
    run_app(root, state)
    accounts = {}
    for alias in ("bootstrap", "owner", "peer"):
        login = "pilot_" + alias + "_" + secrets.token_hex(3)
        secret = secrets.token_urlsafe(24) + "aA1!"
        # This synthetic address is never sent to an email service.
        status, user, _ = api(state["base_url"], "POST", "/users", {
            "email": login + "@" + "example.com", "username": login,
            "password": secret})
        expected = "system_user system_admin" if alias == "bootstrap" else "system_user"
        if status != 201 or set(user.get("roles", "").split()) != set(expected.split()):
            raise RuntimeError("host account bootstrap roles differ from the approved setup")
        accounts[alias] = {"id": user["id"], "login_id": login, "password": secret}
    write_private(root / "bootstrap.json", accounts.pop("bootstrap"))
    write_private(root / "accounts.json", accounts)
    write_private(root / "environment.json", {
        "images": IMAGES, "database_image": DATABASE_IMAGE,
        "application_platform": "linux/amd64", "database_platform": "linux/arm64",
        "base_url": state["base_url"], "published_address": "loopback only",
        "configuration": {key: value for key, value in app_env.items() if key != "MM_SQLSETTINGS_DATASOURCE"},
        "accounts": {key: {"id": value["id"], "role": "system_user"} for key,value in accounts.items()},
        "bootstrap_first": True, "business_objects_created_by_host": False,
        "network_external_access": True,
    })
    print(json.dumps({"status": "ready", "version": state["version"], "base_url": state["base_url"]}))


def upgrade(root):
    state = json.loads((root / "state.json").read_text())
    if state["version"] != "11.7.15":
        raise RuntimeError("upgrade requires the frozen baseline")
    capture_logs(root, state)
    command(root, "stop", "-t", "30", state["app"])
    command(root, "rm", state["app"])
    state["version"] = "11.11.4"
    state["app"] = state["prefix"] + "-app-b"
    run_app(root, state)
    print(json.dumps({"status": "ready", "version": state["version"], "base_url": state["base_url"], "database": "retained"}))


def cleanup(root):
    state = json.loads((root / "state.json").read_text())
    capture_logs(root, state)
    # Verify ownership of exact recorded resources before destructive removal.
    for kind, names in (("container", [state["app"], state["database"]]),
                        ("volume", [state["volume"]]), ("network", [state["network"]])):
        for name in names:
            data = json.loads(command(root, kind, "inspect", name))[0]
            labels = data.get("Config", {}).get("Labels", {}) if kind == "container" else data.get("Labels", {})
            if LABEL not in (labels or {}):
                raise RuntimeError("resource ownership label is missing")
    for name in (state["app"], state["database"]):
        command(root, "stop", "-t", "30", name)
        command(root, "rm", name)
    command(root, "volume", "rm", state["volume"])
    command(root, "network", "rm", state["network"])
    write_private(root / "cleanup.json", {"completed_utc": stamp(), "resources": state, "removed": True})
    print("Dedicated pilot resources removed; local evidence retained.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("start", "upgrade", "cleanup"))
    parser.add_argument("--directory", type=Path, required=True)
    args = parser.parse_args()
    root = args.directory.resolve()
    root.mkdir(parents=True, exist_ok=True)
    os.chmod(root, 0o700)
    {"start": start, "upgrade": upgrade, "cleanup": cleanup}[args.action](root)


if __name__ == "__main__":
    main()
