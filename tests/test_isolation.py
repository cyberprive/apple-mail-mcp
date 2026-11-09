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


def _log_files():
    logger = logging.getLogger("apple_mail_mcp")
    return [Path(h.baseFilename).resolve() for h in logger.handlers
            if isinstance(h, logging.FileHandler)]


def test_log_lands_in_a_temp_folder_not_the_real_log():
    files = _log_files()
    assert REAL_LOG.resolve() not in files
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
