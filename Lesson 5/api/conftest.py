import os
import tempfile
from pathlib import Path

import pytest

# Les tests travaillent sur une base jetable : la variable doit etre posee
# avant l'import de database.py, qui lit l'URL au chargement.
_tmp = tempfile.TemporaryDirectory()
os.environ["DATABASE_URL"] = f"sqlite:///{Path(_tmp.name) / 'tests.db'}"

from fastapi.testclient import TestClient  # noqa: E402

from database import Base, engine  # noqa: E402
from main import app  # noqa: E402


@pytest.fixture
def client():
    # Une base vide pour chaque test.
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    with TestClient(app) as c:
        yield c


@pytest.fixture
def alice(client):
    return client.post("/adduser", json={
        "name": "alice", "email": "alice@example.com", "nickname": "al",
    }).json()


def pytest_sessionfinish(session, exitstatus):
    engine.dispose()
    _tmp.cleanup()
