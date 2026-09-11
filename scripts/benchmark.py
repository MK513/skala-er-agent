"""Performance measurement requires a connected runner and end-to-end API scenarios."""

import sys


def main() -> int:
    print(
        "BLOCKED: the real agent pipeline is not connected and verified end to end. "
        "P50/P90 recommendation latency, repeat-query latency, API/model calls, cache hits "
        "and retry rates have not been measured. Run python scripts/verify.py for offline "
        "checks and blocker details. Resolve integration errors and validate API scenarios "
        "before adding a separately opted-in live benchmark.",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
