# Tiny local chat

This folder is a standalone project. Run all commands below from this folder; the parent `kaggle/` directory is not needed after cloning.

## First run

Requires Python 3.12+ and internet access for dependency installation and the initial model download:

```bash
bash setup_chat.sh
./run.sh
```

On a fresh checkout, setup creates a local `.venv` and downloads the model to `models/huggingface/`. In the original workspace, the launchers can also reuse an existing `../.venv`; use that interpreter path for manual commands if applicable.

## Repository contents

The `.gitignore` in this folder excludes downloaded models, model weights, virtual environments, caches, datasets, build artifacts, logs, and secrets. These files stay on your machine and are downloaded or generated during setup on another machine. Source files, `pyproject.toml`, launch scripts, and this README belong in the repository. Do not include the parent `kaggle/` folder.

## Streamlit web app

```bash
./run.sh
```

Open **http://localhost:8501**. The launcher installs missing dependencies into `.venv` and starts Streamlit. Stop with Ctrl+C. Set `PORT=8502 ./run.sh` for another port.

The web app reuses the downloaded SmolLM2-135M-Instruct model, caches it in memory, streams replies, and defaults to two CPU threads, greedy decoding, and 48-token replies. Change reply length or try experimental dynamic INT8 in the sidebar. INT8 is off by default because it changed answers adversely in local checks. The default uses cached model files only; turn that off to download missing files. Chat history is held in the current browser session, not saved to disk.

The app answers identity questions from its own configuration. Other answers are model-generated and can be incorrect, including basic facts. A smaller model does not guarantee better accuracy. For dependable factual answers, use verified source retrieval or a stronger model.

Measured on this machine (i5-5300U, two inference threads): a short FP32 reply to “What is the capital of France?” took about 0.6 seconds. INT8 generated longer answers in about 1.6–1.8 seconds and introduced errors. These are different outputs, not a controlled speed comparison, browser latency measurement, or accuracy score.

Uses [HuggingFaceTB/SmolLM2-135M-Instruct](https://huggingface.co/HuggingFaceTB/SmolLM2-135M-Instruct) for text-to-text conversation on CPU. The model has 135 million parameters and about 269 MB of model weights. Python dependencies require additional disk space. It primarily supports English and has limited reasoning and factual accuracy.

## Set up and chat

Run in this directory (Python 3.12):

```bash
bash setup_chat.sh
.venv/bin/python chat.py
```

Setup installs CPU PyTorch and Transformers into `.venv`, then downloads the model into `models/huggingface/`. No Kaggle account or API key is needed for this public model. Internet is required for the first setup.

Type `/exit` to quit or `/reset` to clear conversation history. Old turns are dropped when the chat reaches the context budget.

For one reply:

```bash
.venv/bin/python chat.py --prompt "Explain Python in two sentences."
```

After downloading, run without network access:

```bash
.venv/bin/python chat.py --offline
```

Use `--max-new-tokens 64` for shorter replies. This script generates text locally; it does not search the internet.

## Earlier Kaggle BERT example

Downloads the latest version of `anam1ka/prajjwal1bert-tiny/transformers/default` using KaggleHub.

## Setup

```bash
python3.12 -m venv .venv
.venv/bin/python -m ensurepip --upgrade --default-pip
.venv/bin/python -m pip install -e .
```

## Run

```bash
.venv/bin/python main.py
```

Model files are cached under `models/` in this directory, and the script prints their path. An existing `KAGGLEHUB_CACHE` environment variable overrides this location.

Use the explicit `.venv/bin/python -m pip` command if bare `pip` reports an externally managed environment: bare `pip` may resolve to the system installation.

## Use the model

Install inference dependencies (PyTorch can be a large download), then encode text:

```bash
.venv/bin/python -m pip install -e '.[inference]'
.venv/bin/python use_model.py "I love learning Python."
```

The example loads the Kaggle model locally and prints a mean-pooled text embedding with shape `(1, 128)`. These are numerical text features, not a sentiment prediction or generated answer. Tiny BERT is a pretrained text encoder; train it with labeled examples for tasks such as spam detection or sentiment classification. It is not a conversational model. Raw mean-pooled embeddings are a starting point and are not tuned for sentence similarity.

References: [model card](https://huggingface.co/prajjwal1/bert-tiny), [BERT documentation](https://huggingface.co/docs/transformers/model_doc/bert).
# tiny-chatbot
