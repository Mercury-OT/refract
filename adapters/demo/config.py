"""Configuration for the reference demo adapters."""
from dataclasses import dataclass


@dataclass(frozen=True)
class DemoConfig:
    base_url: str
