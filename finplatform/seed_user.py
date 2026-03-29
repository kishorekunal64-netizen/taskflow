"""Seed admin user. Run: python finplatform/seed_user.py"""
import bcrypt
import psycopg2

conn = psycopg2.connect(
    host="localhost", port=5432,
    dbname="finintelligence_db",
    user="postgres", password="taskflow123"
)
cur = conn.cursor()
cur.execute("SELECT user_id FROM users WHERE email = %s", ("royrules19@gmail.com",))
if cur.fetchone():
    print("User already exists: royrules19@gmail.com")
else:
    pw = bcrypt.hashpw(b"Admin@123", bcrypt.gensalt()).decode()
    cur.execute(
        "INSERT INTO users (email, password_hash, role) VALUES (%s, %s, 'admin')",
        ("royrules19@gmail.com", pw)
    )
    conn.commit()
    print("Admin created: royrules19@gmail.com / Admin@123")
cur.close()
conn.close()
