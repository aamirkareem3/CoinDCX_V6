import sqlite3
from contextlib import closing

DB = "trading.db"


def connect():
    return sqlite3.connect(DB)


def init_db():
    with closing(connect()) as conn:
        cur = conn.cursor()

        cur.execute("""
        CREATE TABLE IF NOT EXISTS trades(
            id INTEGER PRIMARY KEY AUTOINCREMENT,

            trade_id TEXT UNIQUE,
            symbol TEXT,
            side TEXT,

            status TEXT,

            entry_time TEXT,
            exit_time TEXT,

            entry_price REAL,
            exit_price REAL,

            stop_loss REAL,
            target REAL,

            quantity REAL,
            leverage INTEGER,

            fees REAL,

            gross_pnl REAL,
            net_pnl REAL,

            r_multiple REAL,

            strategy_score INTEGER,
            confirmation TEXT,

            reason TEXT,

            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)

        conn.commit()


def execute(query, values=()):
    with closing(connect()) as conn:
        cur = conn.cursor()
        cur.execute(query, values)
        conn.commit()


def fetch(query, values=()):
    with closing(connect()) as conn:
        cur = conn.cursor()
        cur.execute(query, values)
        return cur.fetchall()


if __name__ == "__main__":
    init_db()
    print("Trading database initialized.")
