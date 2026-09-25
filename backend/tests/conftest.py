import os

import pytest

os.environ.setdefault("ARGUS_LLM", "off")   # tests never call the API

from argus import settings  # noqa: E402
from argus.config import site  # noqa: E402

# a supervisor PIN in someone's .env must not change what the tests expect; the PIN test sets its own
os.environ.pop("ARGUS_SUPERVISOR_PIN", None)

needs_data = pytest.mark.skipif(
    not (settings.ANNOTATION_DIR.exists() and settings.GPS_DIR.exists()),
    reason="MEVA annotations/GPS not present in data/meva (see scripts/)",
)


@pytest.fixture(scope="session")
def cfg():
    return site()
