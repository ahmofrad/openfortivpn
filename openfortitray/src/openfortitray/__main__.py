"""Entry point for OpenFortiTray."""

import sys


def main() -> int:
    if "--run-helper" in sys.argv:
        # Run as the privileged helper daemon (launched elevated)
        from openfortitray.core.helper import main as helper_main

        return helper_main()

    from openfortitray.app import main as app_main

    return app_main()


if __name__ == "__main__":
    sys.exit(main())
