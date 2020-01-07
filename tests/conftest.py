import tempfile

import pytest


@pytest.fixture
def dirpath():
    with tempfile.TemporaryDirectory(prefix='aiohttp-session-') as dirpath:
        yield dirpath
