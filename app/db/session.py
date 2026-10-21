"""Short transactions; no SQLite lock is held during LLM requests."""
from contextlib import contextmanager
import sqlite3
from app.db.models import SCHEMA

class Database:
    def __init__(self, path):
        self.path = path

    def connect(self):
        db = sqlite3.connect(self.path, timeout=15, check_same_thread=False)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        db.execute("PRAGMA busy_timeout=15000")
        return db

    def initialize(self):
        db = self.connect()
        try:
            db.execute("PRAGMA journal_mode=WAL")
            db.executescript(SCHEMA)
            db.commit()
        finally:
            db.close()

    @contextmanager
    def transaction(self):
        db = self.connect()
        try:
            db.execute("BEGIN IMMEDIATE")
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def all(self, sql, args=()):
        db = self.connect()
        try:
            return [dict(row) for row in db.execute(sql, args).fetchall()]
        finally:
            db.close()

    def one(self, sql, args=()):
        rows = self.all(sql, args)
        return rows[0] if rows else None
