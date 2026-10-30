"""Optional browser support for product-owned Refract adapters."""

from ._support import BrowserSupport
from ._policy import ApiEndpoint, BrowserNetworkPolicy

__all__ = ["BrowserSupport", "ApiEndpoint", "BrowserNetworkPolicy"]
