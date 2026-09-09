"""One container per process, reached through the app rather than a module
global, so a test can build an app around a container with a fake graph."""

from __future__ import annotations

from typing import Any

from fastapi import Request


def get_container(request: Request) -> Any:
    return request.app.state.container
