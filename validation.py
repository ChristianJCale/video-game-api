"""Input validation helpers for the games API."""
import math
import re
import uuid
from datetime import date
from decimal import Decimal

REQUIRED_FIELDS = ["title", "developer", "releaseDate", "price"]

# These limits match the column sizes in sql/schema.sql, so bad input is
# rejected with a 400 response instead of failing inside the database.
MAX_TITLE_LENGTH = 200
MAX_DEVELOPER_LENGTH = 200
MAX_IMAGE_URL_LENGTH = 500
MAX_PRICE = 99999999.99

# [0-9] (not \d) so that non-ASCII digits are rejected too
_DATE_PATTERN = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")


def parse_date(value):
    """Return a date for a strict YYYY-MM-DD string, or None if it isn't a real date."""
    if not isinstance(value, str) or not _DATE_PATTERN.fullmatch(value):
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:  # e.g. 2026-02-30 or 2026-13-01
        return None


def normalize_game_id(value):
    """Return the canonical lowercase UUID string, or None if value isn't a UUID."""
    try:
        return str(uuid.UUID(str(value)))
    except (ValueError, TypeError):
        return None


def validate_game(data):
    """Return an error message if the game data is invalid, otherwise None."""
    if not isinstance(data, dict):
        return "Request body must be a JSON object."

    missing = [
        field for field in REQUIRED_FIELDS
        if field not in data or data[field] in (None, "")
    ]
    if missing:
        return f"Missing required field(s): {', '.join(missing)}."

    for field in ("title", "developer", "releaseDate"):
        if not isinstance(data[field], str):
            return f"'{field}' must be a string."

    if len(data["title"]) > MAX_TITLE_LENGTH:
        return f"'title' must be {MAX_TITLE_LENGTH} characters or fewer."
    if len(data["developer"]) > MAX_DEVELOPER_LENGTH:
        return f"'developer' must be {MAX_DEVELOPER_LENGTH} characters or fewer."

    if parse_date(data["releaseDate"]) is None:
        return "'releaseDate' must be a valid date in YYYY-MM-DD format."

    price = data["price"]
    # bool is a subclass of int in Python, so exclude it explicitly
    if isinstance(price, bool) or not isinstance(price, (int, float)):
        return "'price' must be a number."
    # JSON parsers can produce NaN and Infinity; neither is a real price
    if isinstance(price, float) and not math.isfinite(price):
        return "'price' must be a finite number."
    if price < 0:
        return "'price' cannot be negative."
    if price > MAX_PRICE:
        return f"'price' cannot be greater than {MAX_PRICE:.2f}."
    # The database stores two decimal places; reject extra precision rather than round silently
    if Decimal(str(price)).as_tuple().exponent < -2:
        return "'price' cannot have more than 2 decimal places."

    # imageUrl is optional; null is allowed and means "no image"
    image_url = data.get("imageUrl")
    if image_url is not None:
        if not isinstance(image_url, str):
            return "'imageUrl' must be a string."
        if len(image_url) > MAX_IMAGE_URL_LENGTH:
            return f"'imageUrl' must be {MAX_IMAGE_URL_LENGTH} characters or fewer."
        if not image_url.startswith(("http://", "https://")):
            return "'imageUrl' must start with http:// or https://."

    return None
