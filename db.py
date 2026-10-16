"""Stocare SQLite: produsele și istoricul de prețuri supraviețuiesc restartului."""
import sqlite3
import time

import config

_conn = sqlite3.connect(config.DB_PATH, check_same_thread=False)
_conn.row_factory = sqlite3.Row
_conn.executescript("""
PRAGMA journal_mode=WAL;
CREATE TABLE IF NOT EXISTS products (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id      INTEGER NOT NULL,
    name         TEXT NOT NULL,
    url          TEXT NOT NULL,
    selector     TEXT,
    target_price REAL,
    last_price   REAL,
    currency     TEXT,
    in_stock     INTEGER,
    method       TEXT,
    fail_count   INTEGER NOT NULL DEFAULT 0,
    last_checked REAL,
    created_at   REAL NOT NULL,
    UNIQUE (chat_id, url)
);
CREATE TABLE IF NOT EXISTS prices (
    product_id INTEGER NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    price      REAL NOT NULL,
    in_stock   INTEGER,
    ts         REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_prices_product ON prices(product_id, ts);
""")
_conn.execute("PRAGMA foreign_keys=ON")


def add_product(chat_id, name, url, selector=None):
    """Întoarce id-ul produsului (nou sau existent pentru același URL)."""
    with _conn:
        _conn.execute(
            "INSERT INTO products (chat_id, name, url, selector, created_at) VALUES (?,?,?,?,?) "
            "ON CONFLICT(chat_id, url) DO UPDATE SET name=excluded.name, "
            "selector=COALESCE(excluded.selector, products.selector)",
            (chat_id, name, url, selector or None, time.time()),
        )
    return _conn.execute("SELECT id FROM products WHERE chat_id=? AND url=?", (chat_id, url)).fetchone()["id"]


def get_product(chat_id, product_id):
    return _conn.execute("SELECT * FROM products WHERE id=? AND chat_id=?", (product_id, chat_id)).fetchone()


def list_products(chat_id=None):
    if chat_id is None:
        return _conn.execute("SELECT * FROM products ORDER BY id").fetchall()
    return _conn.execute("SELECT * FROM products WHERE chat_id=? ORDER BY id", (chat_id,)).fetchall()


def remove_product(chat_id, product_id):
    with _conn:
        return _conn.execute("DELETE FROM products WHERE id=? AND chat_id=?", (product_id, chat_id)).rowcount


def update_fields(product_id, **fields):
    cols = ", ".join(f"{k}=?" for k in fields)
    with _conn:
        _conn.execute(f"UPDATE products SET {cols} WHERE id=?", (*fields.values(), product_id))


def record_success(product_id, price, currency, in_stock, method):
    now = time.time()
    with _conn:
        _conn.execute(
            "UPDATE products SET last_price=?, currency=COALESCE(?, currency), in_stock=?, method=?, "
            "fail_count=0, last_checked=? WHERE id=?",
            (price, currency, in_stock, method, now, product_id),
        )
        # Salvăm în istoric doar când prețul/stocul se schimbă -> DB rămâne mică.
        last = _conn.execute(
            "SELECT price, in_stock FROM prices WHERE product_id=? ORDER BY ts DESC LIMIT 1", (product_id,)
        ).fetchone()
        if last is None or last["price"] != price or last["in_stock"] != in_stock:
            _conn.execute("INSERT INTO prices VALUES (?,?,?,?)", (product_id, price, in_stock, now))


def record_failure(product_id):
    with _conn:
        _conn.execute(
            "UPDATE products SET fail_count=fail_count+1, last_checked=? WHERE id=?", (time.time(), product_id)
        )
    return _conn.execute("SELECT fail_count FROM products WHERE id=?", (product_id,)).fetchone()["fail_count"]


def history(product_id, limit=15):
    return _conn.execute(
        "SELECT price, in_stock, ts FROM prices WHERE product_id=? ORDER BY ts DESC LIMIT ?", (product_id, limit)
    ).fetchall()


def price_stats(product_id):
    return _conn.execute(
        "SELECT MIN(price) AS min, MAX(price) AS max, COUNT(*) AS n FROM prices WHERE product_id=?", (product_id,)
    ).fetchone()
