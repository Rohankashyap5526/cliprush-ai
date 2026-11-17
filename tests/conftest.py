import os
import tempfile

# Must be set before `app` is imported anywhere: config creates its data folders at import time.
_DATA = tempfile.mkdtemp(prefix="cliprush-test-")
os.environ["CLIPRUSH_DATA_DIR"] = _DATA
os.environ["CLIPRUSH_AUTH_USERNAME"] = "tester"
os.environ["CLIPRUSH_AUTH_PASSWORD"] = "s3cret-password"
os.environ.pop("CLIPRUSH_DISABLE_AUTH", None)
