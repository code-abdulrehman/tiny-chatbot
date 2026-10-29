"""Shared CPU inference for local chat."""
import os
import re
from hashlib import sha256
from pathlib import Path
from threading import Event, Lock, Thread

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer, TextIteratorStreamer, StoppingCriteria, StoppingCriteriaList

DEFAULT_MODEL = 'HuggingFaceTB/SmolLM2-135M-Instruct'
CACHE_DIR = Path(__file__).resolve().parent / 'models' / 'huggingface'
ENGINE_REVISION = sha256(Path(__file__).read_bytes()).hexdigest()
SYSTEM = ('You are Tiny Chat, an AI assistant, not a person. '
          'Answer briefly in one or two sentences. '
          'If you do not know the answer, say you do not know. Do not invent facts.')


def identity_reply(text):
    """Use app configuration for identity instead of model invention."""
    normalized = re.sub(r'[^a-z ]', '', text.lower()).strip()
    if normalized in {'what is your name', 'whats your name', 'whats you name', 'who are you', 'your name'}:
        return "I'm Tiny Chat, a local AI assistant powered by SmolLM2."
    return None


def clean_title(text, user_prompt):
    title = text.strip().split('\n')[0]
    title = re.sub(r'^(?:title|topic)\s*:\s*', '', title, flags=re.IGNORECASE)
    title = re.sub(r'[*#`"<>]', '', title).strip(" '.:-")
    title = ' '.join(title.split()[:5])[:48].strip()
    normalize = lambda value: ' '.join(re.findall(r'\w+', value.casefold()))
    # Never fall back to copying the user's prompt.
    if not title or normalize(title) == normalize(user_prompt) or title.lower().startswith(('here is', 'here are')):
        return 'New conversation'
    return title


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
        self.context_limit = self.model.config.max_position_embeddings

    def generate_title(self, history):
        """Summarize a thread once with a small, separate generation budget."""
        excerpt = '\n'.join(f"{m['role']}: {m['content'][:300]}" for m in history[:2])
        messages = [
            {'role': 'system', 'content': 'Write only a short topic title of 2 to 5 words. No quotes, explanation, or answer.'},
            {'role': 'user', 'content': 'user: Explain how Python lists work.\nTitle:'},
            {'role': 'assistant', 'content': 'Python List Basics'},
            {'role': 'user', 'content': excerpt + '\nTitle:'},
        ]
        prompt = self.tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        inputs = self.tokenizer(prompt, return_tensors='pt', add_special_tokens=False)
        with self.lock, torch.inference_mode():
            output = self.model.generate(
                **inputs, max_new_tokens=12, do_sample=False,
                repetition_penalty=1.1, use_cache=True,
                pad_token_id=self.tokenizer.eos_token_id)
        title = self.tokenizer.decode(output[0, inputs['input_ids'].shape[1]:], skip_special_tokens=True)
        return clean_title(title, history[0]['content'])

    def prepare_inputs(self, history, max_new_tokens=48, context_tokens=1024, continue_reply=False):
        if context_tokens not in {256, 512, 1024, 2048, 4096, 8192}:
            raise ValueError('Unsupported context length.')
        limit = min(context_tokens, self.context_limit)
        messages = [{'role': 'system', 'content': SYSTEM}] + [dict(m) for m in history]
        while True:
            template_options = ({'continue_final_message': True} if continue_reply else {'add_generation_prompt': True})
            prompt = self.tokenizer.apply_chat_template(messages, tokenize=False, **template_options)
            inputs = self.tokenizer(prompt, return_tensors='pt', add_special_tokens=False)
            if inputs['input_ids'].shape[1] + max_new_tokens <= limit:
                return inputs
            if len(messages) <= (3 if continue_reply else 2):
                raise ValueError('Message exceeds the context budget. Shorten it or increase context length in Settings.')
            del messages[1:3]

    def stream(self, history, max_new_tokens=48, context_tokens=1024, sample=False, continue_reply=False, generation_status=None):
        fixed = None if continue_reply else identity_reply(history[-1]['content'])
        if fixed:
            yield fixed
            return
        inputs = self.prepare_inputs(history, max_new_tokens, context_tokens, continue_reply)
        streamer = TextIteratorStreamer(self.tokenizer, skip_prompt=True, skip_special_tokens=True)
        errors = []
        cancelled = Event()

        class CancelGeneration(StoppingCriteria):
            def __call__(self, input_ids, scores, **kwargs):
                return cancelled.is_set()

        def generate():
            try:
                with torch.inference_mode():
                    output = self.model.generate(
                        **inputs, streamer=streamer, max_new_tokens=max_new_tokens,
                        do_sample=sample, repetition_penalty=1.1, use_cache=True,
                        stopping_criteria=StoppingCriteriaList([CancelGeneration()]),
                        **({'temperature': 0.7, 'top_p': 0.9} if sample else {}),
                        pad_token_id=self.tokenizer.eos_token_id)
                    if generation_status is not None:
                        eos = self.model.generation_config.eos_token_id
                        eos = eos if isinstance(eos, list) else [eos]
                        eos = set(eos + [self.tokenizer.eos_token_id])
                        generated = output.shape[1] - inputs['input_ids'].shape[1]
                        generation_status['truncated'] = generated >= max_new_tokens and output[0, -1].item() not in eos
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
                cancelled.set()
                worker.join()
            if errors:
                raise RuntimeError(f'Generation failed: {errors[0]}') from errors[0]
