import hmac
import json
import logging
import os

import azure.functions as func

import repository
from validation import normalize_game_id, validate_game
from keyvault_auth import get_api_key

app = func.FunctionApp(http_auth_level=func.AuthLevel.ANONYMOUS)


def json_response(body, status_code=200):
    """Return a JSON HTTP response with the given status code."""
    return func.HttpResponse(
        json.dumps(body),
        status_code=status_code,
        mimetype="application/json",
    )


def check_api_key(req: func.HttpRequest):
    """Check the x-api-key header against the api-key secret in Azure Key Vault.

    Returns None when the key is valid, otherwise an error response
    (401 for a missing/wrong key, 500 if the key can't be read from Key Vault).
    The key lives only in Key Vault, never in the code or an app setting.
    """
    provided = req.headers.get("x-api-key")
    if not provided:
        # Checked first so unauthenticated requests never cause a Key Vault call
        return json_response({"error": "Missing or invalid API key."}, 401)

    try:
        expected = get_api_key()
    except Exception:
        # Fail closed: never allow access just because the key couldn't be read
        logging.exception("Could not read the API key from Key Vault")
        return json_response({"error": "Server API key is not configured."}, 500)

    # compare_digest avoids leaking information through comparison timing
    if not hmac.compare_digest(provided.encode("utf-8"), expected.encode("utf-8")):
        return json_response({"error": "Missing or invalid API key."}, 401)

    return None


def error_response_for(exc):
    """Log an unexpected error and return a safe, generic response.

    Must be called from inside an except block so the traceback is logged.
    The client never sees database details or stack traces.
    """
    if isinstance(exc, repository.DatabaseUnavailableError):
        logging.exception("Database unavailable")
        return json_response(
            {"error": "Database temporarily unavailable. Please try again."}, 503
        )
    logging.exception("Unexpected error")
    return json_response({"error": "Internal server error."}, 500)


def not_found_response(game_id):
    return json_response({"error": f"Game with id '{game_id}' not found."}, 404)


# Routes for the collection: /api/games
def create_game(req: func.HttpRequest) -> func.HttpResponse:
    """POST /api/games -- create a new game."""
    try:
        data = req.get_json()
    except ValueError:
        return json_response({"error": "Request body must be valid JSON."}, 400)

    error = validate_game(data)
    if error:
        return json_response({"error": error}, 400)

    # The server generates the UUID; upcoming, isFree and validatedOn start at their defaults
    return json_response(repository.create_game(data), 201)


def list_games(req: func.HttpRequest) -> func.HttpResponse:
    """GET /api/games -- return all games."""
    return json_response(repository.list_games(), 200)


@app.route(route="games", methods=["GET", "POST"])
def games_collection(req: func.HttpRequest) -> func.HttpResponse:
    auth_error = check_api_key(req)
    if auth_error:
        return auth_error

    try:
        if req.method == "POST":
            return create_game(req)
        return list_games(req)
    except Exception as exc:
        return error_response_for(exc)


# Routes for a single game: /api/games/{id}
def get_game(game_id: str) -> func.HttpResponse:
    """GET /api/games/{id} -- return one game."""
    game = repository.get_game(game_id)
    if game is None:
        return not_found_response(game_id)
    return json_response(game, 200)


def update_game(req: func.HttpRequest, game_id: str) -> func.HttpResponse:
    """PUT /api/games/{id} -- replace the editable fields of an existing game."""
    # Existence is checked first so a missing game is always 404, even with a bad body
    if repository.get_game(game_id) is None:
        return not_found_response(game_id)

    try:
        data = req.get_json()
    except ValueError:
        return json_response({"error": "Request body must be valid JSON."}, 400)

    error = validate_game(data)
    if error:
        return json_response({"error": error}, 400)

    game = repository.update_game(game_id, data)
    if game is None:  # deleted by someone else between the two calls
        return not_found_response(game_id)
    return json_response(game, 200)


def delete_game(game_id: str) -> func.HttpResponse:
    """DELETE /api/games/{id} -- remove a game."""
    if not repository.delete_game(game_id):
        return not_found_response(game_id)
    return json_response({"message": "Game deleted.", "id": game_id}, 200)


@app.route(route="games/{id}", methods=["GET", "PUT", "DELETE"])
def games_item(req: func.HttpRequest) -> func.HttpResponse:
    auth_error = check_api_key(req)
    if auth_error:
        return auth_error

    raw_id = req.route_params.get("id")
    game_id = normalize_game_id(raw_id)
    if game_id is None:
        # Not a UUID, so it can't exist: same 404 as any other unknown id
        return not_found_response(raw_id)

    try:
        if req.method == "GET":
            return get_game(game_id)
        if req.method == "PUT":
            return update_game(req, game_id)
        return delete_game(game_id)
    except Exception as exc:
        return error_response_for(exc)
