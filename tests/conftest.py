"""Keep the test suite off the user's real files.

The server reads its settings once, when apple_mail_mcp.config is first
imported, and opens its log file at that point too. So the environment has to
be set before any test module imports apple_mail_mcp. That is why this runs at
module level: pytest imports conftest.py before it collects the tests.

Without it, the tests that fake a Mail error or a timeout write those as real
ERROR lines into ~/Library/Logs/apple-mail-mcp.log, the same file the user's
running server logs to.
"""
import os
import shutil
import tempfile
from pathlib import Path

SANDBOX = Path(tempfile.mkdtemp(prefix="apple-mail-mcp-tests-"))
os.environ["APPLE_MAIL_MCP_LOG_PATH"] = str(SANDBOX / "test.log")
os.environ["APPLE_MAIL_MCP_ATTACHMENTS_DIR"] = str(SANDBOX / "attachments")


def pytest_unconfigure(config):
    shutil.rmtree(SANDBOX, ignore_errors=True)
