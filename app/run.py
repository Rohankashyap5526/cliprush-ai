"""Explicit Render entry point with startup diagnostics and dynamic port binding."""
import os
import logging
import uvicorn


def main() -> None:
    port = int(os.environ.get("PORT", "10000"))
    logging.basicConfig(level=logging.INFO)
    logging.getLogger("cliprush").info(
        "Starting ClipRush AI on 0.0.0.0:%s", port
    )
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=port,
        log_level=os.environ.get("LOG_LEVEL", "info").lower(),
        access_log=True,
    )


if __name__ == "__main__":
    main()
