from backend.app.api.routes.health import health
from backend.app.core.config import Settings


def test_health_endpoint() -> None:
    response = health(Settings())

    assert response.status == "ok"
