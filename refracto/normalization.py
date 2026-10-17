"""Shared minimal ResponseNormalizer port-result validation."""
import copy

from refracto.ports import NormalizedResponse, RequestSpec
from refracto.declaration.values import equal
from refracto.projection.recording import _evidence_equal
from refracto import headers as header_ops


def normalize_response(normalizer, response):
    """Malformed port output is an execution error, not unavailable field data."""
    protected_request = copy.deepcopy(response.request)
    protected_headers = {name: copy.deepcopy(getattr(response, name))
                         for name in ("request_header_items", "header_items")}
    supplied = copy.deepcopy(response)
    norm = header_ops.call_port("Normalizer", normalizer.normalize, supplied,
                                sensitive=header_ops.recorded(response))
    if (not isinstance(norm, NormalizedResponse) or type(norm.succeeded) is not bool
            or not isinstance(norm.fields, dict)
            or any(type(key) is not str for key in norm.fields)):
        raise ValueError("Normalizer must return NormalizedResponse with boolean succeeded and string-keyed fields")
    # Normalized fields may be returned without raw evidence under the existing
    # minimal port contract. If the normalizer returns a request-bearing raw
    # value, it must retain the protected query just as its supplied copy must.
    raw_request = getattr(norm.raw, "request", None)
    if (type(supplied.request) is not RequestSpec
            or not equal(supplied.request.query, protected_request.query)
            or (raw_request is not None and (type(raw_request) is not RequestSpec
                or not equal(raw_request.query, protected_request.query)))):
        raise ValueError("Normalizer changed request query evidence")
    if (not _evidence_equal(supplied.request.headers, protected_request.headers)
            or (raw_request is not None and not _evidence_equal(raw_request.headers, protected_request.headers))):
        raise ValueError("Normalizer changed request business headers")
    for name, expected in protected_headers.items():
        if (not _evidence_equal(getattr(supplied, name, None), expected)
                or (norm.raw is not None and not _evidence_equal(getattr(norm.raw, name, None), expected))):
            raise ValueError("Normalizer changed protected header evidence")
    return norm
