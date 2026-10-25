"""Database URLs.

Settings hold libpq URLs (``postgresql://...``), which psycopg uses as they are.
SQLAlchemy needs the driver in the scheme.
"""


def sqlalchemy_url(libpq_url: str) -> str:
    """``postgresql://...`` -> ``postgresql+psycopg://...``."""
    scheme, separator, rest = libpq_url.partition("://")
    if not separator or scheme not in {"postgresql", "postgres"}:
        raise ValueError("expected a postgresql:// URL")
    return f"postgresql+psycopg://{rest}"
