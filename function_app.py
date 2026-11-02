import hmac
import json
import os
import uuid

import azure.functions as func

app = func.FunctionApp(http_auth_level=func.AuthLevel.ANONYMOUS)

# In-memory repository: a plain list that holds every game while the app is running.
# There is no database, so data is lost when the app restarts or scales.
games = []

REQUIRED_FIELDS = ["title", "developer", "releaseDate", "price"]


def json_response(body, status_code=200):
    """Return a JSON HTTP response with the given status code."""
    return func.HttpResponse(
        json.dumps(body),
        status_code=status_code,
        mimetype="application/json",
    )


def check_api_key(req: func.HttpRequest):
    """Check the x-api-key header.

    Returns None when the key is valid, otherwise an error response
    (401 for a missing/wrong key, 500 if the server has no key configured).
    The real key lives in the API_KEY app setting, never in the code.
    """
    expected = os.environ.get("API_KEY")
    if not expected:
        # Fail closed: never allows access just because the setting is missing
        return json_response({"error": "Server API key is not configured."}, 500)

    provided = req.headers.get("x-api-key")
    if not provided:
        return json_response({"error": "Missing or invalid API key."}, 401)

    # compare_digest avoids leaking information through comparison timing
    if not hmac.compare_digest(provided.encode("utf-8"), expected.encode("utf-8")):
        return json_response({"error": "Missing or invalid API key."}, 401)

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

    price = data["price"]
    # bool is a subclass of int in Python, so exclude it explicitly
    if isinstance(price, bool) or not isinstance(price, (int, float)):
        return "'price' must be a number."
    if price < 0:
        return "'price' cannot be negative."

    return None


def create_game(req: func.HttpRequest) -> func.HttpResponse:
    """POST /api/games -- create a new game."""
    try:
        data = req.get_json()
    except ValueError:
        return json_response({"error": "Request body must be valid JSON."}, 400)

    error = validate_game(data)
    if error:
        return json_response({"error": error}, 400)

    game = {
        "id": str(uuid.uuid4()),  # the server generates the unique ID
        "title": data["title"],
        "developer": data["developer"],
        "releaseDate": data["releaseDate"],
        "price": data["price"],
    }
    games.append(game)
    return json_response(game, 201)


def list_games(req: func.HttpRequest) -> func.HttpResponse:
    """GET /api/games -- return all games."""
    return json_response(games, 200)


@app.route(route="games", methods=["GET", "POST"])
def games_collection(req: func.HttpRequest) -> func.HttpResponse:
    auth_error = check_api_key(req)
    if auth_error:
        return auth_error

    if req.method == "POST":
        return create_game(req)
    return list_games(req)


# Routes for a single game: /api/games/{id}
def find_game(game_id):
    """Return the game with this ID, or None if it doesn't exist."""
    for game in games:
        if game["id"] == game_id:
            return game
    return None


def update_game(req: func.HttpRequest, game_id: str) -> func.HttpResponse:
    """PUT /api/games/{id} -- replace the fields of an existing game."""
    game = find_game(game_id)
    if game is None:
        return json_response({"error": f"Game with id '{game_id}' not found."}, 404)

    try:
        data = req.get_json()
    except ValueError:
        return json_response({"error": "Request body must be valid JSON."}, 400)

    error = validate_game(data)
    if error:
        return json_response({"error": error}, 400)

    # Update the stored game in place
    game["title"] = data["title"]
    game["developer"] = data["developer"]
    game["releaseDate"] = data["releaseDate"]
    game["price"] = data["price"]
    return json_response(game, 200)


def delete_game(req: func.HttpRequest, game_id: str) -> func.HttpResponse:
    """DELETE /api/games/{id} -- remove a game."""
    game = find_game(game_id)
    if game is None:
        return json_response({"error": f"Game with id '{game_id}' not found."}, 404)

    games.remove(game)
    return json_response({"message": "Game deleted.", "id": game_id}, 200)


@app.route(route="games/{id}", methods=["PUT", "DELETE"])
def games_item(req: func.HttpRequest) -> func.HttpResponse:
    auth_error = check_api_key(req)
    if auth_error:
        return auth_error

    game_id = req.route_params.get("id")
    if req.method == "PUT":
        return update_game(req, game_id)
    return delete_game(req, game_id)