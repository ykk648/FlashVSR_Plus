from __future__ import annotations

import argparse
import os


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the FlashVSR+ FastAPI service")
    parser.add_argument("--host", default=os.getenv("FLASHVSR_PLUS_HOST", "0.0.0.0"))
    parser.add_argument("--port", type=int, default=int(os.getenv("FLASHVSR_PLUS_PORT", "18303")))
    parser.add_argument("--device", default=os.getenv("FLASHVSR_PLUS_DEVICE", "cuda:0"))
    args = parser.parse_args()
    os.environ["FLASHVSR_PLUS_DEVICE"] = args.device
    import uvicorn
    uvicorn.run("flashvsr_plus_api.main:app", host=args.host, port=args.port, workers=1)


if __name__ == "__main__":
    main()
