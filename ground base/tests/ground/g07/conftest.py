"""Run coroutine tests with the standard library. pytest-asyncio is not required."""

from __future__ import annotations

import asyncio
import inspect

import pytest


@pytest.hookimpl(tryfirst=True)
def pytest_pyfunc_call(pyfuncitem: pytest.Function) -> bool | None:
    testfunction = pyfuncitem.obj
    if not inspect.iscoroutinefunction(testfunction):
        return None
    kwargs = {
        name: pyfuncitem.funcargs[name]
        for name in inspect.signature(testfunction).parameters
    }
    asyncio.run(testfunction(**kwargs))
    return True
