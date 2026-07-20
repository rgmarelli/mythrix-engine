"""`Stores` is built once at process startup (`app.py`'s `lifespan`) and
read from `app.state` per request — never rebuilt per request."""

from __future__ import annotations

from fastapi import Request

from mythrix.core.bootstrap import Stores


def get_stores(request: Request) -> Stores:
    return request.app.state.stores
