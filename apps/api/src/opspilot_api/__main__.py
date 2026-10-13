import os

import uvicorn


def run() -> None:
    uvicorn.run(
        "opspilot_api.main:create_app",
        factory=True,
        host=os.environ.get("API_HOST", "127.0.0.1"),
        port=int(os.environ.get("API_PORT", "8000")),
        access_log=False,
        # Proxy headers are handled inside the app with an explicit trust list.
        proxy_headers=False,
    )


if __name__ == "__main__":
    run()
