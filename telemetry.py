"""Custom Application Insights telemetry: events and SQL dependency spans.

Nothing here can break a request. If the Azure Monitor packages are missing or
telemetry isn't configured (for example in a local run), these helpers do nothing.
"""
import logging
from contextlib import nullcontext

try:
    from azure.monitor.events.extension import track_event
except ImportError:  # package not installed
    track_event = None

try:
    from opentelemetry import trace

    _tracer = trace.get_tracer(__name__)
except ImportError:  # package not installed
    trace = None
    _tracer = None


def emit_event(name, properties=None):
    """Send a custom event (shows up in the customEvents table). Never raises.

    Application Insights custom dimensions are strings, so every value is converted.
    """
    if track_event is None:
        return
    try:
        track_event(name, {key: str(value) for key, value in (properties or {}).items()})
    except Exception:
        logging.warning("custom_event_failed name=%s", name, exc_info=True)


def sql_span():
    """Wrap a block of database work in a client span so it appears as a SQL dependency."""
    if _tracer is None:
        return nullcontext()
    return _tracer.start_as_current_span(
        "azure-sql",
        kind=trace.SpanKind.CLIENT,
        attributes={"db.system": "mssql", "db.name": "sqldb-videogames"},
    )
