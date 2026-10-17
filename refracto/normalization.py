"""Shared minimal ResponseNormalizer port-result validation."""
import copy

from refracto.ports import NormalizedResponse


def normalize_response(normalizer, response):
    """Malformed port output is an execution error, not unavailable field data."""
    norm = normalizer.normalize(copy.deepcopy(response))
    if (not isinstance(norm, NormalizedResponse) or type(norm.succeeded) is not bool
            or not isinstance(norm.fields, dict)
            or any(type(key) is not str for key in norm.fields)):
        raise ValueError("Normalizer must return NormalizedResponse with boolean succeeded and string-keyed fields")
    return norm
