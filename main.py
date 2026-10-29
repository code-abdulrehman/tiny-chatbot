"""Download the latest BERT Tiny model files from Kaggle."""

import os
from pathlib import Path

# Keep downloaded files in this project instead of the user-wide cache.
os.environ.setdefault("KAGGLEHUB_CACHE", str(Path(__file__).resolve().parent / "models"))

import kagglehub


def main() -> None:
    path = kagglehub.model_download("anam1ka/prajjwal1bert-tiny/transformers/default")
    print("Path to model files:", path)


if __name__ == "__main__":
    main()
