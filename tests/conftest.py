"""pytest configuration and fixtures."""

from __future__ import annotations

import inspect
import tempfile
from pathlib import Path

import aioresponses.core
import pytest
from aiohttp import ClientResponse


class _UnsentRequestWriter:
    """Stand-in writer for a request aioresponses never actually sent."""

    output_size = 0


if "stream_writer" in inspect.signature(ClientResponse.__init__).parameters:
    # aiohttp 3.14 made stream_writer a required argument of ClientResponse.
    # aioresponses (0.7.9, the latest) builds its fake responses by calling
    # ClientResponse directly and does not pass it, so every mocked request
    # fails with TypeError. Fill it in until aioresponses catches up.
    # aioresponses passes writer=None, so aiohttp only reads output_size off
    # it and then forgets it.
    class _CompatClientResponse(ClientResponse):
        def __init__(self, *args: object, **kwargs: object) -> None:
            kwargs.setdefault("stream_writer", _UnsentRequestWriter())
            super().__init__(*args, **kwargs)  # type: ignore[arg-type]

    aioresponses.core.ClientResponse = _CompatClientResponse


@pytest.fixture
def temp_dir():
    with tempfile.TemporaryDirectory() as d:
        yield Path(d)
