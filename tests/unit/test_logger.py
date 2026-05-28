import json
import logging
import sys

from app.logger import JsonFormatter


def test_json_formatter_emits_valid_json_with_extra():
    formatter = JsonFormatter()
    record = logging.LogRecord(
        name="pipeline",
        level=logging.INFO,
        pathname="x.py",
        lineno=1,
        msg="stage %s done",
        args=("screener",),
        exc_info=None,
    )
    record.stage = "screener"
    record.candidate_count = 3

    parsed = json.loads(formatter.format(record))

    assert parsed["level"] == "INFO"
    assert parsed["logger"] == "pipeline"
    assert parsed["message"] == "stage screener done"
    assert parsed["stage"] == "screener"
    assert parsed["candidate_count"] == 3
    assert "ts" in parsed


def test_json_formatter_serializes_nested_payload():
    formatter = JsonFormatter()
    record = logging.LogRecord(
        name="pipeline",
        level=logging.INFO,
        pathname="x.py",
        lineno=1,
        msg="done",
        args=(),
        exc_info=None,
    )
    record.result = [{"symbol": "BTC", "score": 7}]

    parsed = json.loads(formatter.format(record))

    assert parsed["result"] == [{"symbol": "BTC", "score": 7}]


def test_json_formatter_colorize_wraps_in_ansi_and_stays_unwrappable():
    record = logging.LogRecord(
        name="pipeline",
        level=logging.WARNING,
        pathname="x.py",
        lineno=1,
        msg="careful",
        args=(),
        exc_info=None,
    )

    plain = JsonFormatter(colorize=False).format(record)
    colored = JsonFormatter(colorize=True).format(record)

    assert json.loads(plain)["message"] == "careful"
    assert colored.startswith("\033[")
    assert colored.endswith("\033[0m")
    assert json.dumps("careful") in colored


def test_json_formatter_includes_exception():
    formatter = JsonFormatter()
    try:
        raise ValueError("boom")
    except ValueError:
        record = logging.LogRecord(
            name="pipeline",
            level=logging.ERROR,
            pathname="x.py",
            lineno=1,
            msg="failed",
            args=(),
            exc_info=sys.exc_info(),
        )

    parsed = json.loads(formatter.format(record))

    assert "ValueError" in parsed["exc"]
