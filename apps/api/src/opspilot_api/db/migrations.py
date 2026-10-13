from pathlib import Path

from alembic.config import Config

# Shipped inside the package so container images can migrate without the repo.
MIGRATIONS_DIR = Path(__file__).resolve().parent / "alembic"


def alembic_config(database_url: str) -> Config:
    """Alembic config for this service, independent of the working directory."""
    config = Config()
    config.set_main_option("script_location", str(MIGRATIONS_DIR))
    config.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))
    return config
