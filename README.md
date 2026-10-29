# Tiny local chat

For the separate browser-only edition with on-device Qwen2.5 inference and browser-local chats, see [browser/README.md](browser/README.md).

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

Open the URL printed by the launcher (normally **http://localhost:8501**). If that port is busy, the launcher selects the next available port without stopping other processes. It installs missing dependencies into `.venv` and starts Streamlit. Stop with Ctrl+C. Set `PORT=8502 ./run.sh` to start checking from another port.

The web app reuses the downloaded SmolLM2-135M-Instruct model, caches it in memory, streams replies, and defaults to two CPU threads, greedy decoding, and a 256-token default reply limit (existing saved preferences are preserved). Open Settings at the bottom of the sidebar to change reply length, context length (256–8192 tokens), or try experimental dynamic INT8. Context includes instructions, retained conversation, and reserved reply tokens; the actual model limit is always respected. Longer context uses more CPU and RAM. Old complete turns are dropped when the budget is full. INT8 is off by default because it changed answers adversely in local checks. The default uses cached model files only; turn that off to download missing files. Regular conversations are saved locally in `data/chats.sqlite3` and can be reopened after restarting the app. The sidebar includes New chat, search across titles and messages, and a list of saved conversations. The native Private chat toggle is positioned at the top right beside Streamlit’s header toolbar. Thread titles are left-aligned and truncate with an ellipsis; each row uses a single three-dot action icon. New saved threads get a short AI-generated topic title after their first reply; titles are generated only once with a 12-token budget. If title generation fails, the app uses “New conversation” instead of copying the prompt. Switching private mode starts a fresh conversation; New chat keeps the selected mode, and opening a saved thread returns to saved mode. Private chats remain only in session memory and are discarded when you switch chats or end the session; they never enter the database or saved-chat search. Each saved thread has a three-dot menu for Rename, Duplicate, and Delete. Delete requires confirmation; duplicates have independent IDs and messages. AI titles are generated from the opening exchange after the first reply, and manually renamed titles are preserved. The model receives as many recent turns as the selected context budget allows. Local chat data is excluded from Git. This is a single-user local app: anyone with access to the running app can see saved conversations.

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

## Tests

From this folder, run `.venv/bin/python -m unittest discover -s tests -v` (or use `../.venv/bin/python` for the original workspace). Tests use temporary databases and do not load the model.

The model cache is keyed by the engine source revision. Streamlit reloads an outdated engine module and creates a fresh model instance when the inference code changes, preventing stale method-signature errors during development.

Each user and assistant message has a Copy control. Clipboard writes happen in the browser, without rerunning Python or saving clipboard content. A selection-based fallback handles browsers without Clipboard API access; if both methods are blocked, the control reports that the text must be selected manually.

Copy and Retry controls appear together at the bottom right when hovering or keyboard-focusing a message; they stay visible on touch devices. Message time remains visible next to them at all times. Only the latest assistant reply has Retry. Retrying replaces that reply while preserving the user message and thread title; a failed retry keeps the previous reply. Retries use mild sampling, so a different answer is possible but not guaranteed. Every new message stores its UTC timestamp and displays the time at bottom right in the browser timezone (UTC fallback). Older messages with no recorded timestamp display “—”.

Saved chats have a stable, unique 10-character slug in the URL (`?chat=...`). Reloading the page reopens that saved conversation from the local database. Renaming preserves the slug; duplicating creates a new one. Existing databases are migrated automatically without losing messages. New chat and Private chat clear the chat URL, and invalid/deleted links open a fresh conversation. Slugs resolve against this installation’s local database. The sidebar shows Tiny Chat branding at the top and Settings at the bottom.

Tiny Chat uses Streamlit’s native logo slot alongside the sidebar collapse button. The sidebar keeps Settings at the bottom while only the thread list scrolls. Each thread’s menu appears on row hover or keyboard focus, remains visible while open, and stays visible on touch devices.

Chat settings (reply length, context length, INT8, and offline mode) are persisted locally in the SQLite database when Save settings is clicked and restored after refresh or app restart. Preferences apply to this local installation; private chat content and private-mode state are not saved as preferences.

Reply length supports up to 1024 tokens per generation. The context budget must exceed the reply limit so there is room for instructions and conversation. When a reply hits its token limit, Continue appends generated text to that same answer; the last answer always offers Continue alongside Retry. Continuation preserves the user message and title, and a failure keeps the previous answer.

Floating up/down arrows at the bottom right scroll smoothly to the first or latest message. They appear only when that direction is useful, run entirely in the browser, and honor reduced-motion preferences. Thread menu buttons use neutral header-style hover feedback.

Continue is a visible button below the latest response in the chat area. During continuation, the existing reply stays rendered while the model loads, then new chunks update the same message in place. The logo uses a fixed brand color that remains readable in both light and dark themes without waiting for a Python rerun.

Replies now continue automatically when a generation chunk hits its token limit, until the model emits an end token. Reply length controls each chunk, not the combined response. If context is exhausted or the model produces no new text, generation pauses with a reason and the manual Continue button remains available. The chat input offers Stop during generation; partial text is retained and can be resumed. Closing the stream signals the CPU generation worker to stop.
