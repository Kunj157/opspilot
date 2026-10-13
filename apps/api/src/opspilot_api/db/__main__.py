"""Run Alembic against DATABASE_URL: python -m opspilot_api.db <alembic args>."""

import sys

from alembic.config import CommandLine

from opspilot_api.config import get_settings
from opspilot_api.db.migrations import alembic_config


def main() -> None:
    url = get_settings().database_url
    if not url:
        sys.exit("DATABASE_URL is not set")
    cli = CommandLine(prog="python -m opspilot_api.db")
    options = cli.parser.parse_args(sys.argv[1:])
    if not hasattr(options, "cmd"):
        cli.parser.error("too few arguments")
    cli.run_cmd(alembic_config(url), options)


if __name__ == "__main__":
    main()
