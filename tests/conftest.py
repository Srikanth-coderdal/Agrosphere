"""Point the app at a throwaway SQLite file before any test imports it."""
import os
import tempfile

_TEST_DB_DIR = tempfile.mkdtemp(prefix="agrosphere_test_")
_TEST_DB_PATH = os.path.join(_TEST_DB_DIR, "test.db").replace("\\", "/")
os.environ["AGROSPHERE_DB_URL"] = "sqlite:///" + _TEST_DB_PATH
