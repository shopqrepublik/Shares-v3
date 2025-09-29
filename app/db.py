import os, psycopg2
from psycopg2.extras import RealDictCursor

def get_conn():
    url = os.getenv("DATABASE_URL")
    return psycopg2.connect(url, cursor_factory=RealDictCursor)
