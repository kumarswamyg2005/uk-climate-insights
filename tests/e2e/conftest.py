import pytest


@pytest.fixture(scope="session", autouse=True)
def _allow_orm_next_to_playwright():
    """Playwright's sync API runs an event loop on the test thread, and Django's async-safety check
    would then refuse ORM calls in test setup. Scoped to this package's session, so it only applies
    when browser tests are selected; the normal run keeps the check."""
    with pytest.MonkeyPatch.context() as patch:
        patch.setenv("DJANGO_ALLOW_ASYNC_UNSAFE", "true")
        yield
