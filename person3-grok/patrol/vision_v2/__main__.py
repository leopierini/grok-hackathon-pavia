"""Real vision transport entrypoint. Host, port, and auth are unset."""

from __future__ import annotations

import sys


def main() -> int:
    sys.stderr.write(
        "patrol.vision_v2: real mode exits 2; /ws/robot/v2 host, port, and auth are unset\n"
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
