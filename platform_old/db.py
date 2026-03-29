import os
from contextlib import contextmanager
from psycopg2.pool import ThreadedConnectionPool

_pool: ThreadedConnectionPool | None = None


def init_pool() -> None:
    global _pool
    _pool = ThreadedConnectionPool(
        minconn=2,
        maxconn=10,
        host=os.environ["DB_HOST"],
        port=os.environ.get("DB_PORT", "5432"),
        dbname=os.environ["DB_NAME"],
        user=os.environ["DB_USER"],
        password=os.environ["DB_PASSWORD"],
    )


@contextmanager
def get_conn():
    """Yield a connection from the pool, returning it on exit (even on exception)."""
    conn = _pool.getconn()
    try:
        yield conn
    finally:
        _pool.putconn(conn)


def close_pool() -> None:
    if _pool:
        _pool.closeall()
