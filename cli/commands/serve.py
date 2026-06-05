import uvicorn

from core.settings import settings


def api() -> None:
    """Запускает analytics REST/WebSocket API (uvicorn) на host:port из настроек."""
    uvicorn.run(
        "app.engines.api.server:app",
        host=settings.API_HOST,
        port=settings.API_PORT,
        log_config=None,
    )
