"""
One-time setup script:
1. Creates the finintelligence_db database (if not exists)
2. Applies schema.sql
3. Seeds an admin user

Run from C:\taskflow:
    python finplatform/setup_db.py
"""

import os
import sys
import psycopg2
from psycopg2 import sql
import bcrypt as _bcrypt

# ── Config ────────────────────────────────────────────────────────────────────
DB_HOST = "localhost"
DB_PORT = "5432"
DB_NAME = "finintelligence_db"
DB_USER = "postgres"
DB_PASSWORD = "taskflow123"

ADMIN_EMAIL = "royrules19@gmail.com"
ADMIN_PASSWORD = "Admin@123"   # change this

SCHEMA_PATH = os.path.join(os.path.dirname(__file__), "schema.sql")


def hash_password(password: str) -> str:
    return _bcrypt.hashpw(password.encode(), _bcrypt.gensalt()).decode()


def create_database():
    """Create the database if it doesn't exist."""
    conn = psycopg2.connect(
        host=DB_HOST, port=DB_PORT,
        dbname="postgres",  # connect to default db first
        user=DB_USER, password=DB_PASSWORD,
    )
    conn.autocommit = True
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (DB_NAME,))
    if not cur.fetchone():
        cur.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(DB_NAME)))
        print(f"Created database: {DB_NAME}")
    else:
        print(f"Database already exists: {DB_NAME}")
    cur.close()
    conn.close()


def apply_schema(conn):
    """Apply schema.sql to the database."""
    with open(SCHEMA_PATH, "r") as f:
        schema_sql = f.read()
    with conn.cursor() as cur:
        cur.execute(schema_sql)
    conn.commit()
    print("Schema applied.")


def seed_admin(conn):
    """Insert admin user if not already present."""
    with conn.cursor() as cur:
        cur.execute("SELECT user_id FROM users WHERE email = %s", (ADMIN_EMAIL,))
        if cur.fetchone():
            print(f"Admin user already exists: {ADMIN_EMAIL}")
            return
        password_hash = hash_password(ADMIN_PASSWORD)
        cur.execute(
            "INSERT INTO users (email, password_hash, role) VALUES (%s, %s, 'admin')",
            (ADMIN_EMAIL, password_hash),
        )
    conn.commit()
    print(f"Admin user created: {ADMIN_EMAIL} / {ADMIN_PASSWORD}")


if __name__ == "__main__":
    print("Setting up FinIntelligence database...")

    try:
        create_database()
    except Exception as e:
        print(f"ERROR creating database: {e}")
        sys.exit(1)

    try:
        conn = psycopg2.connect(
            host=DB_HOST, port=DB_PORT,
            dbname=DB_NAME, user=DB_USER, password=DB_PASSWORD,
        )
    except Exception as e:
        print(f"ERROR connecting to {DB_NAME}: {e}")
        sys.exit(1)

    try:
        apply_schema(conn)
        seed_admin(conn)
        print("\nSetup complete!")
        print(f"  DB:    {DB_NAME}")
        print(f"  Login: {ADMIN_EMAIL}")
        print(f"  Pass:  {ADMIN_PASSWORD}")
    except Exception as e:
        print(f"ERROR during setup: {e}")
        conn.rollback()
        sys.exit(1)
    finally:
        conn.close()
