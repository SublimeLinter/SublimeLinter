
import pytest


@pytest.fixture
def unstub():
    from mockito import unstub
    yield
    unstub()
