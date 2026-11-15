"""Bounded local snapshots for fixed single-file actions.

One loaded composition counts a canonical source pathname once, even when it
is referenced by several leaves. Different pathnames (including hard links)
count separately. Only the loader sees local paths; ports receive byte values.
"""
import hashlib
import os
import re
import stat
from dataclasses import dataclass
from pathlib import Path

from refracto.ports import UploadFile

_TOKEN = re.compile(r"[!#$%&'*+.^_`|~0-9A-Za-z-]+", re.ASCII)
_DIGEST = re.compile(r"[0-9a-f]{64}", re.ASCII)


@dataclass(frozen=True, slots=True)
class FileConfig:
    max_file_bytes: int = 10 * 1024 * 1024
    max_total_bytes: int = 64 * 1024 * 1024

    def __post_init__(self):
        if any(type(value) is not int or value <= 0
               for value in (self.max_file_bytes, self.max_total_bytes)):
            raise ValueError("file budgets must be strict positive integers")


def descriptors(value):
    """Validate syntax without touching any asset or interpreting references."""
    if type(value) is not dict or len(value) != 1:
        raise ValueError("files must contain exactly one literal upload field")
    name, descriptor = next(iter(value.items()))
    if type(name) is not str or _TOKEN.fullmatch(name) is None:
        raise ValueError("upload field must be a literal HTTP token")
    if type(descriptor) is not dict or set(descriptor) != {"path", "sha256"}:
        raise ValueError("file descriptor requires exactly path and sha256")
    path, digest = descriptor["path"], descriptor["sha256"]
    if (type(path) is not str or not path or path.startswith("/")
            or any(c in path for c in ("\x00", "\\", ":", "*", "?", "[", "]", "$", "~"))
            or any(part in ("", ".", "..") for part in path.split("/"))
            or any(ord(c) < 32 or ord(c) == 127 for c in path)):
        raise ValueError("file path must be a literal contained relative local path")
    if type(digest) is not str or _DIGEST.fullmatch(digest) is None:
        raise ValueError("file fingerprint must be lowercase SHA-256")
    return {name: {"path": path, "sha256": digest}}


def require_text_body(body, files, *, unknown=()):
    if body is None or any(body is item for item in unknown):
        return
    if type(body) is not dict:
        raise ValueError("upload body must be a flat mapping of text fields")
    if set(body) & set(files):
        raise ValueError("upload text and file fields must not overlap")
    if any(type(key) is not str or not key or type(value) is not str
           and not any(value is item for item in unknown) for key, value in body.items()):
        raise ValueError("upload body values must be strings")


def known_body(body, parameters):
    from refracto.declaration.run_values import known_value
    body = known_value(body, parameters)
    if type(body) is dict:
        return {key: known_value(value, parameters) for key, value in body.items()}
    return body


def require_files(value):
    if value is None:
        return
    if type(value) is not dict or len(value) != 1:
        raise ValueError("prepared files must contain exactly one upload")
    name, asset = next(iter(value.items()))
    if (type(name) is not str or _TOKEN.fullmatch(name) is None
            or type(asset) is not UploadFile or type(asset.filename) is not str
            or not asset.filename or asset.filename in (".", "..")
            or any(c in asset.filename for c in ("/", "\\"))
            or any(ord(c) < 32 or ord(c) == 127 for c in asset.filename)
            or type(asset.data) is not bytes or type(asset.sha256) is not str
            or _DIGEST.fullmatch(asset.sha256) is None
            or hashlib.sha256(asset.data).hexdigest() != asset.sha256):
        raise ValueError("prepared upload requires a safe filename and verified immutable bytes")


def require_file(value):
    """Validate one selected or observed immutable file without a source path."""
    require_files({"file": value})


def require_browser_file(value):
    """Reject filename spellings ambiguous under browser multipart escaping."""
    require_file(value)
    if '"' in value.filename or re.search(r"%(?:22|0a|0d)", value.filename, re.IGNORECASE):
        raise ValueError("browser upload filename escaping is unsupported")


def same_files(actual, expected):
    require_files(actual)
    require_files(expected)
    return actual == expected


class AssetSnapshots:
    def __init__(self, config=None):
        if config is not None and type(config) is not FileConfig:
            raise ValueError("file_config must be FileConfig")
        self.config = config if config is not None else FileConfig()
        self.cache = {}
        self.total = 0

    def read(self, base, descriptor):
        if base is None:
            raise ValueError("upload requires its declaring Scenario source directory")
        if any(not hasattr(os, flag) for flag in ("O_DIRECTORY", "O_NOFOLLOW", "O_NONBLOCK")):
            raise ValueError("safe local file snapshots are unsupported on this platform")
        base = Path(base).resolve()
        parts = descriptor["path"].split("/")
        identity = base.joinpath(*parts)
        if identity in self.cache:
            asset = self.cache[identity]
            if asset.sha256 != descriptor["sha256"]:
                raise ValueError("file fingerprint mismatch")
            return asset
        limit = min(self.config.max_file_bytes, self.config.max_total_bytes - self.total)
        handles = []
        try:
            directory = os.open(base, os.O_RDONLY | os.O_DIRECTORY)
            handles.append(directory)
            for part in parts[:-1]:
                directory = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                                    dir_fd=directory)
                handles.append(directory)
            fd = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                         dir_fd=directory)
            handles.append(fd)
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode):
                raise ValueError("upload asset must be a regular file")
            if info.st_size > limit:
                raise ValueError("upload asset exceeds file or composition byte budget")
            chunks, size = [], 0
            while True:
                chunk = os.read(fd, min(65536, limit - size + 1))
                if not chunk:
                    break
                size += len(chunk)
                if size > limit:
                    raise ValueError("upload asset exceeds file or composition byte budget")
                chunks.append(chunk)
            data = b"".join(chunks)
        except (AttributeError, NotImplementedError, TypeError):
            raise ValueError("safe local file snapshots are unsupported on this platform") from None
        except OSError:
            raise ValueError("upload asset is unsafe, missing or inaccessible") from None
        finally:
            for handle in reversed(handles):
                os.close(handle)
        digest = hashlib.sha256(data).hexdigest()
        if digest != descriptor["sha256"]:
            raise ValueError("file fingerprint mismatch")
        asset = UploadFile(filename=parts[-1], data=data, sha256=digest)
        self.total += len(data)
        self.cache[identity] = asset
        return asset

    def freeze(self, scenario):
        for step in scenario.steps:
            if step.file_descriptor is not None:
                step.file = self.read(step._file_base, step.file_descriptor)
                step._file_base = None
            request = step.request
            if request is not None and request.file_descriptors is not None:
                request.files = {name: self.read(request._file_base, descriptor)
                                 for name, descriptor in request.file_descriptors.items()}
                request._file_base = None
        return scenario


def preflight(scenario, api=None, *, capability=True, api_requests_only=False):
    """Reject every invalid or unsupported upload before any action/authentication."""
    present = False
    from refracto.declaration.run_values import UNKNOWN, STRING
    for step in scenario.steps:
        if step.action == "select_file":
            if (type(step.target) is not str or not step.target.strip()
                    or step.value is not None or step.key is not None
                    or step.duration is not None or step.object_id is not None
                    or step.poll is not None or step.object_poll is not None
                    or step.request is not None or step.request_asserted
                    or step.expect.response or step.expect.backend_state):
                raise ValueError("UI file selection requires a literal target and UI expectations only")
            require_file(step.file)
        elif step.file is not None or step.file_descriptor is not None:
            raise ValueError("file is only supported on select_file steps")
        request = step.request
        if request is None:
            continue
        if request.file_descriptors is not None and request.files is None:
            raise ValueError("upload assets have not been frozen")
        if request.files is None:
            continue
        present = present or not api_requests_only or step.action == "request"
        if (step.poll is not None or not (
                step.action == "request" and not step.request_asserted
                or step.action == "click" and step.request_asserted)):
            raise ValueError("uploads require an explicit API action or declared click request")
        require_files(request.files)
        body = known_body(request.body, scenario.parameters)
        require_text_body(body, request.files, unknown=(UNKNOWN, STRING))
    if present and capability:
        callback = getattr(api, "supports_file_upload", None)
        try:
            supported = callable(callback) and callback() is True
        except Exception:
            raise ValueError("API file upload capability check failed") from None
        if not supported:
            raise ValueError("API file upload capability not supported")
