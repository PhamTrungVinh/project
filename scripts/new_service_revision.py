"""Create an Alembic revision for one service after updating its owned models."""

import argparse

from alembic import command
from alembic.config import Config

from service_migrations.common import ROOT, SERVICE_TABLES, database_url


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("service", choices=sorted(SERVICE_TABLES))
    parser.add_argument("message")
    parser.add_argument("--database-url", help="Service database URL for autogeneration")
    args = parser.parse_args()

    configuration = Config()
    configuration.set_main_option("script_location", str(ROOT / args.service))
    configuration.attributes["database_url"] = args.database_url or database_url(args.service)
    command.revision(configuration, message=args.message, autogenerate=True)


if __name__ == "__main__":
    main()
