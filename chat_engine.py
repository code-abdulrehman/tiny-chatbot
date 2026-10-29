"""Shared CPU inference for local chat."""
import os
import re
from pathlib import Path
from threading import Lock, Thread

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer, TextIteratorStreamer

DEFAULT_MODEL = 'HuggingFaceTB/SmolLM2-135M-Instruct'
CACHE_DIR = Path(__file__).resolve().parent / 'models' / 'huggingface'
SYSTEM = ('You are Tiny Chat, an AI assistant, not a person. '
          'Answer briefly in one or two sentences. '
          'If you do not know the answer, say you do not know. Do not invent facts.')


def identity_reply(text):
    """Use app configuration for identity instead of model invention."""
    normalized = re.sub(r'[^a-z ]', '', text.lower()).strip()
    if normalized in {'what is your name', 'whats your name', 'whats you name', 'who are you', 'your name'}:
        return "I'm Tiny Chat, a local AI assistant powered by SmolLM2."
    return None


class ChatEngine:
    def __init__(self, quantized=False, offline=True):
        torch.set_num_threads(max(1, int(os.environ.get('CHAT_THREADS', '2'))))
        options = {'cache_dir': str(CACHE_DIR), 'local_files_only': offline}
        self.tokenizer = AutoTokenizer.from_pretrained(DEFAULT_MODEL, **options)
        self.model = AutoModelForCausalLM.from_pretrained(
            DEFAULT_MODEL, dtype=torch.float32, use_safetensors=True, **options
        ).eval()
        if quantized:
            import warnings
            with warnings.catch_warnings():
                warnings.simplefilter('ignore', DeprecationWarning)
                self.model = torch.ao.quantization.quantize_dynamic(
                    self.model, {torch.nn.Linear}, dtype=torch.qint8)
        self.lock = Lock()
        self.context_limit = min(self.model.config.max_position_embeddings, 1024)

    def stream(self, history, max_new_tokens=48):
        fixed = identity_reply(history[-1]['content'])
        if fixed:
            yield fixed
            return
        messages = [{'role': 'system', 'content': SYSTEM}] + [dict(m) for m in history[-7:]]
        while True:
            prompt = self.tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
            inputs = self.tokenizer(prompt, return_tensors='pt', add_special_tokens=False)
            if inputs['input_ids'].shape[1] + max_new_tokens <= self.context_limit:
                break
            if len(messages) <= 2:
                raise ValueError('Please shorten your message; it exceeds the context budget.')
            del messages[1:3]
        streamer = TextIteratorStreamer(self.tokenizer, skip_prompt=True, skip_special_tokens=True)
        errors = []

        def generate():
            try:
                with torch.inference_mode():
                    self.model.generate(
                        **inputs, streamer=streamer, max_new_tokens=max_new_tokens,
                        do_sample=False, repetition_penalty=1.1, use_cache=True,
                        pad_token_id=self.tokenizer.eos_token_id)
            except Exception as exc:
                errors.append(exc)
                streamer.end()

        # Cached resources are shared between sessions; serialize model access.
        with self.lock:
            worker = Thread(target=generate, daemon=True)
            worker.start()
            try:
                yield from streamer
            finally:
                worker.join()
            if errors:
                raise RuntimeError(f'Generation failed: {errors[0]}') from errors[0]
