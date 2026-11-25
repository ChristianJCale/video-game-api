import logging
import os
import struct
import time

import pyodbc
from azure.identity import DefaultAzureCredential

SQL_COPT_SS_ACCESS_TOKEN = 1256  # connection attribute defined by Microsoft's ODBC driver
LOGIN_TIMEOUT_SECONDS = 60       # a paused serverless database can take about a minute to wake
MAX_ATTEMPTS = 4
RETRY_DELAY_SECONDS = 15
# 40613 = database paused/resuming; the others are transient Azure SQL errors
TRANSIENT_CODES = ("40613", "40197", "40501", "49918", "49919", "49920")


def _is_transient(exc):
    return isinstance(exc, pyodbc.OperationalError) or any(
        code in str(exc) for code in TRANSIENT_CODES
    )

_credential = DefaultAzureCredential()


def get_connection():
    """Open a connection to Azure SQL using a Microsoft Entra access token (no password)."""
    server = os.environ["SQL_SERVER"]
    database = os.environ["SQL_DATABASE"]

    # Fail fast with a readable message instead of a long login timeout
    if not server.endswith(".database.windows.net"):
        raise RuntimeError(
            "SQL_SERVER must be the full server name ending in .database.windows.net"
        )

    conn_str = (
        "Driver={ODBC Driver 18 for SQL Server};"
        f"Server=tcp:{server},1433;"
        f"Database={database};"
        "Encrypt=yes;TrustServerCertificate=no;"
    )

    for attempt in range(1, MAX_ATTEMPTS + 1):
        # Fetch a fresh token each attempt so a slow wake-up can't leave us with an expired one
        token = _credential.get_token("https://database.windows.net/.default").token
        token_bytes = token.encode("utf-16-le")
        token_struct = struct.pack(f"<I{len(token_bytes)}s", len(token_bytes), token_bytes)
        try:
            return pyodbc.connect(
                conn_str,
                attrs_before={SQL_COPT_SS_ACCESS_TOKEN: token_struct},
                timeout=LOGIN_TIMEOUT_SECONDS,
            )
        except pyodbc.Error as exc:
            if attempt == MAX_ATTEMPTS or not _is_transient(exc):
                raise
            logging.warning("SQL connection attempt %d failed (%s); retrying in %ds",
                            attempt, exc, RETRY_DELAY_SECONDS)
            time.sleep(RETRY_DELAY_SECONDS)
