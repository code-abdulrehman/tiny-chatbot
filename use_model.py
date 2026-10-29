"""Create a text embedding with the downloaded Tiny BERT model."""

import argparse
from pathlib import Path

from main import kagglehub
import torch
from transformers import AutoModel, AutoTokenizer, BertTokenizer


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("text", nargs="?", default="I am learning machine learning.")
    args = parser.parse_args()

    path = Path(kagglehub.model_download("anam1ka/prajjwal1bert-tiny/transformers/default"))
    # Some model archives wrap the Transformers files in a subdirectory.
    if not (path / "config.json").is_file():
        configs = sorted(path.rglob("config.json"))
        if len(configs) != 1:
            raise RuntimeError(f"Expected one model config.json under {path}; found {len(configs)}")
        path = configs[0].parent

    # Older BERT exports may have only vocab.txt, without tokenizer metadata.
    if (path / "tokenizer_config.json").is_file() or (path / "tokenizer.json").is_file():
        tokenizer = AutoTokenizer.from_pretrained(str(path), local_files_only=True)
    elif (path / "vocab.txt").is_file():
        tokenizer = BertTokenizer(vocab_file=str(path / "vocab.txt"), do_lower_case=True)
    else:
        raise RuntimeError(f"Tokenizer files are missing from {path}")

    model = AutoModel.from_pretrained(str(path), local_files_only=True)
    model.eval()
    inputs = tokenizer(args.text, return_tensors="pt", truncation=True, max_length=512)
    with torch.inference_mode():
        hidden = model(**inputs).last_hidden_state
        mask = inputs["attention_mask"].unsqueeze(-1).to(hidden.dtype)
        embedding = (hidden * mask).sum(dim=1) / mask.sum(dim=1).clamp(min=1)

    print("Text:", args.text)
    print("Embedding shape:", tuple(embedding.shape))
    print("First 8 values:", embedding[0, :8].tolist())


if __name__ == "__main__":
    main()
