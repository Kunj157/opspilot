import os

import uvicorn

from opspilot_demo.app import create_app
from opspilot_demo.settings import Settings
from opspilot_demo.telemetry import configure_logging


def run() -> None:
    configure_logging()
    settings = Settings()  # type: ignore[call-arg]  # service_name comes from SERVICE_NAME
    uvicorn.run(
        create_app(settings),
        host="0.0.0.0",  # noqa: S104 - container port, exposed only through a Service
        port=int(os.environ.get("PORT", "8080")),
        log_config=None,
        access_log=False,
    )


if __name__ == "__main__":
    run()
