"""Public CLI for scenario validation.

`refracto validate <scenario.yaml>` loads a declaration through the same loader
used by the runtime so contract validation has one executable answer.

This module depends only on the declaration layer.
"""
import argparse
import sys

from refracto.declaration.loader import DeclarationError, load_scenario


def _validate(path: str) -> int:
    try:
        s = load_scenario(path)
    except FileNotFoundError:
        print(f"INVALID {path}: file not found", file=sys.stderr)
        return 2
    except DeclarationError as e:
        print(f"INVALID {path}: {e}", file=sys.stderr)
        return 2
    except Exception as e:
        print(f"INVALID {path}: {type(e).__name__}: {e}", file=sys.stderr)
        return 2
    steps = s.steps
    fe = sum(len(st.expect.frontend) for st in steps)
    resp = sum(len(st.expect.response) for st in steps)
    bs = sum(len(st.expect.backend_state) for st in steps)
    reqs = sum(1 for st in steps if st.request is not None)
    print(f"OK {s.id}  grid={s.grid.level}/{s.grid.module}  steps={len(steps)} requests={reqs}  "
          f"asserts: frontend={fe} response={resp} backend_state={bs}")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="refracto")
    sub = parser.add_subparsers(dest="cmd", required=True)
    v = sub.add_parser("validate", help="validate a scenario YAML against the contract")
    v.add_argument("path", help="path to a scenario YAML file")
    args = parser.parse_args(argv)
    if args.cmd == "validate":
        return _validate(args.path)
    return 1
