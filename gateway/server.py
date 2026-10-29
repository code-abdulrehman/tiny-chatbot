"""Run the model gateway with uvicorn."""

import uvicorn

from gateway import config


def main() -> None:
    uvicorn.run("gateway.app:create_app", host=config.HOST, port=config.PORT, factory=True)


if __name__ == "__main__":
    main()
