"""Serve the web UI:  uv run python -m web [--host 127.0.0.1] [--port 8600]"""

from __future__ import annotations

import argparse

import uvicorn

DEV_PORT = 8600


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description="Анық: the web UI over walks")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=DEV_PORT)
    args = ap.parse_args(argv)
    uvicorn.run("web.server:app", host=args.host, port=args.port, server_header=False)


if __name__ == "__main__":
    main()
