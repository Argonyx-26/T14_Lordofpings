import os

import pytest

os.environ.setdefault("ARGUS_LLM", "off")   # tests never call the API

from argus import settings  # noqa: E402
from argus.config import site  # noqa: E402

needs_data = pytest.mark.skipif(
    not (settings.ANNOTATION_DIR.exists() and settings.GPS_DIR.exists()),
    reason="MEVA annotations/GPS not present in data/meva (see scripts/)",
)


@pytest.fixture(scope="session")
def cfg():
    return site()
