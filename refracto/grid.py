"""Scenario grid selection.

`None` acts as a wildcard. When both filters are provided, they combine with
logical AND.
"""


def select(scenario, level=None, module=None) -> bool:
    if level is not None and scenario.grid.level != level:
        return False
    if module is not None and scenario.grid.module != module:
        return False
    return True
