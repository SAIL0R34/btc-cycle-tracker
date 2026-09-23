"""Local pytest helpers for async tests."""

import asyncio
import inspect

import pytest


def pytest_configure(config: pytest.Config) -> None:
    """Register local markers used by the test suite."""
    config.addinivalue_line(
        "markers",
        "asyncio: run the marked test in an asyncio event loop",
    )


@pytest.hookimpl(tryfirst=True)
def pytest_pyfunc_call(pyfuncitem: pytest.Function) -> bool | None:
    """Run asyncio-marked coroutine tests without an external plugin."""
    if "asyncio" not in pyfuncitem.keywords:
        return None

    test_function = pyfuncitem.obj
    if not inspect.iscoroutinefunction(test_function):
        return None

    asyncio.run(test_function(**pyfuncitem.funcargs))
    return True
