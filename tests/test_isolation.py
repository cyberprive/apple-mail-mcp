"""The test suite must not touch the user's real log or attachments folder.

Invariant: everything the suite logs lands in a temporary folder (set up by
conftest.py), never in ~/Library/Logs/apple-mail-mcp.log, the file the user's
running server writes to. The attachments folder is redirected the same way.

The handler is checked before anything is logged, so if the redirect is ever
lost this test fails without adding a line to the real log.
"""
import logging
import tempfile
from pathlib import Path

from apple_mail_mcp import server  # noqa: F401 (importing the server sets up logging)
from apple_mail_mcp.config import SETTINGS

REAL_LOG = Path.home() / "Library" / "Logs" / "apple-mail-mcp.log"
REAL_ATTACHMENTS = Path.home() / "Downloads" / "apple-mail-mcp"
TEMP = Path(tempfile.gettempdir()).resolve()


def _file_handlers():
    logger = logging.getLogger("apple_mail_mcp")
    return [h for h in logger.handlers if isinstance(h, logging.FileHandler)]


def _set_up_by_the_server(handlers):
    # Newer pytest (seen in 9.2.0, not in 9.0.3) also attaches its own
    # log-capture FileHandler — to /dev/null unless --log-file is set — to
    # non-propagating loggers like this one while tests run. That is pytest's
    # capture, not a place the server writes to, so it is left out here. The
    # real-log check below still covers every handler, pytest's included.
    return [h for h in handlers if not type(h).__module__.startswith("_pytest")]


def test_log_lands_in_a_temp_folder_not_the_real_log():
    handlers = _file_handlers()
    assert REAL_LOG.resolve() not in [Path(h.baseFilename).resolve() for h in handlers]
    files = [Path(h.baseFilename).resolve() for h in _set_up_by_the_server(handlers)]
    assert files == [SETTINGS.log_path.resolve()]
    assert files[0].is_relative_to(TEMP), files[0]

    marker = "test-isolation-marker"
    logging.getLogger("apple_mail_mcp.tests").error(marker)
    for h in logging.getLogger("apple_mail_mcp").handlers:
        h.flush()
    assert marker in SETTINGS.log_path.read_text()


def test_attachments_folder_is_a_temp_folder():
    assert SETTINGS.attachments_dir != REAL_ATTACHMENTS
    assert SETTINGS.attachments_dir.resolve().is_relative_to(TEMP)
