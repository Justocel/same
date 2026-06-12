import os
from contextlib import contextmanager

import psycopg


@contextmanager
def connect():
    """Yields a connection; commits on clean exit, rolls back on error."""
    with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
        yield conn
