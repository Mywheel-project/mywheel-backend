import psycopg2
import psycopg2.extras
from fastapi import FastAPI

app = FastAPI(title="mywheel-backend")

DB_CONFIG = {
    "host": "localhost",
    "port": 5432,
    "dbname": "mywheel",
    "user": "mywheel",
    "password": "mywheel",
}


def get_connection():
    return psycopg2.connect(**DB_CONFIG)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/users")
def get_users():
    with get_connection() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT id, name, email, created_at FROM users ORDER BY id;")
            return cur.fetchall()
