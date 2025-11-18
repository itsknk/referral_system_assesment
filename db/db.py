import psycopg
from contextlib import contextmanager


DSN = "dbname=nika user=nika password=secret host=localhost port=5432"


@contextmanager
def get_conn():
    """
    simple context manager to get a Postgres connection.
    autocommit is disabled so we can manage transactions explicitly.
    """
    with psycopg.connect(DSN) as conn:
        conn.autocommit = False
        yield conn

