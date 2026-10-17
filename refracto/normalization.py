"""Shared minimal ResponseNormalizer port-result validation."""
import copy

from refracto.ports import NormalizedResponse, RequestSpec
from refracto.declaration.values import equal


def normalize_response(normalizer, response):
    """Malformed port output is an execution error, not unavailable field data."""
    protected_request = copy.deepcopy(response.request)
    supplied = copy.deepcopy(response)
    norm = normalizer.normalize(supplied)
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
    return norm
