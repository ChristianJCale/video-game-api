"""Game repository: all database access for the games API lives in this module.

function_app.py never writes SQL. It calls these functions, which return plain
dictionaries in the same JSON shape the API has always used.
"""
import uuid
from contextlib import contextmanager
from datetime import date
from decimal import Decimal

import pyodbc

from db import get_connection

# One column list, used by every SELECT, so rows always unpack the same way
COLUMNS = "id, title, developer, releaseDate, price, upcoming, isFree, validatedOn, imageUrl"


class DatabaseUnavailableError(Exception):
    """The database could not be reached (for example, while it resumes from a pause)."""


@contextmanager
def _transaction():
    """Open a connection and yield a cursor.

    Commits when the block succeeds, rolls back when it fails, and always closes
    the connection. Connection failures become DatabaseUnavailableError so the
    API can answer 503 instead of a generic 500.
    """
    try:
        conn = get_connection()
    except pyodbc.OperationalError as exc:
        raise DatabaseUnavailableError(str(exc)) from exc

    try:
        yield conn.cursor()
        conn.commit()
    except Exception as exc:
        try:
            conn.rollback()
        except Exception:
            pass  # the connection may already be gone
        if isinstance(exc, pyodbc.OperationalError):
            raise DatabaseUnavailableError(str(exc)) from exc
        raise
    finally:
        conn.close()


def _row_to_game(row):
    """Convert a database row into the API's JSON shape."""
    (game_id, title, developer, release_date, price,
     upcoming, is_free, validated_on, image_url) = row
    return {
        # SQL Server returns GUIDs in uppercase; the API has always returned lowercase
        "id": str(game_id).lower(),
        "title": title,
        "developer": developer,
        "releaseDate": release_date.isoformat(),
        "price": float(price),
        "upcoming": bool(upcoming),
        "isFree": bool(is_free),
        # validatedOn is stored in UTC
        "validatedOn": validated_on.strftime("%Y-%m-%dT%H:%M:%SZ") if validated_on else None,
        "imageUrl": image_url,
    }


def _fetch_one(cursor, game_id):
    cursor.execute(f"SELECT {COLUMNS} FROM games WHERE id = ?", [game_id])
    return cursor.fetchone()


def list_games():
    """Return every game, in a stable order."""
    with _transaction() as cursor:
        cursor.execute(f"SELECT {COLUMNS} FROM games ORDER BY title, releaseDate, id")
        return [_row_to_game(row) for row in cursor.fetchall()]


def get_game(game_id):
    """Return one game as a dict, or None if it doesn't exist."""
    with _transaction() as cursor:
        row = _fetch_one(cursor, game_id)
    return _row_to_game(row) if row else None


def create_game(data):
    """Insert a game with a new server-generated UUID and return it."""
    game_id = str(uuid.uuid4())
    with _transaction() as cursor:
        cursor.execute(
            "INSERT INTO games (id, title, developer, releaseDate, price, imageUrl) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            [
                game_id,
                data["title"],
                data["developer"],
                date.fromisoformat(data["releaseDate"]),
                Decimal(str(data["price"])),
                data.get("imageUrl"),
            ],
        )
        row = _fetch_one(cursor, game_id)
    return _row_to_game(row)


def update_game(game_id, data):
    """Update a game's client-editable fields. Returns the game, or None if not found.

    imageUrl is optional: leave it out to keep the current value, or send null to clear it.
    The id, upcoming, isFree and validatedOn columns are never changed here.
    """
    # Only fixed, hard-coded column names are ever added to the SQL text;
    # every value goes through a ? parameter.
    assignments = ["title = ?", "developer = ?", "releaseDate = ?", "price = ?"]
    params = [
        data["title"],
        data["developer"],
        date.fromisoformat(data["releaseDate"]),
        Decimal(str(data["price"])),
    ]
    if "imageUrl" in data:
        assignments.append("imageUrl = ?")
        params.append(data["imageUrl"])
    params.append(game_id)

    with _transaction() as cursor:
        cursor.execute(f"UPDATE games SET {', '.join(assignments)} WHERE id = ?", params)
        if cursor.rowcount == 0:
            return None
        row = _fetch_one(cursor, game_id)
    return _row_to_game(row)


def delete_game(game_id):
    """Delete a game. Returns True if a row was deleted, False if it didn't exist."""
    with _transaction() as cursor:
        cursor.execute("DELETE FROM games WHERE id = ?", [game_id])
        return cursor.rowcount > 0
