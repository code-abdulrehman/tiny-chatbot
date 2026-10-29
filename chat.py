"""Run a tiny text-generation chat model locally on CPU."""

import argparse
from pathlib import Path


DEFAULT_MODEL = "HuggingFaceTB/SmolLM2-135M-Instruct"
CACHE_DIR = Path(__file__).resolve().parent / "models" / "huggingface"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prompt", help="Generate one reply and exit.")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="Hugging Face model ID or local folder.")
    parser.add_argument("--max-new-tokens", type=int, default=128)
    parser.add_argument("--offline", action="store_true", help="Use cached files only.")
    parser.add_argument("--download-only", action="store_true", help="Cache model files and exit.")
    args = parser.parse_args()
    if args.max_new_tokens < 1 or args.max_new_tokens > 512:
        parser.error("--max-new-tokens must be between 1 and 512")

    try:
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer
    except ImportError as exc:
        parser.exit(1, f"Missing dependency: {exc}\nRun: bash setup_chat.sh\n")

    print(f"Loading {args.model} on CPU...", flush=True)
    options = {"cache_dir": str(CACHE_DIR), "local_files_only": args.offline}
    tokenizer = AutoTokenizer.from_pretrained(args.model, **options)
    model = AutoModelForCausalLM.from_pretrained(
        args.model, dtype=torch.float32, use_safetensors=True, **options
    ).to("cpu")
    model.eval()
    if args.download_only:
        print(f"Model ready. Cache: {CACHE_DIR}")
        return

    system = {"role": "system", "content": "You are a helpful assistant. Give short, clear answers."}
    messages = [system]
    context_limit = min(getattr(model.config, "max_position_embeddings", 2048), 2048)

    def reply(text: str) -> str:
        messages.append({"role": "user", "content": text})
        while True:
            prompt = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
            inputs = tokenizer(prompt, add_special_tokens=False, return_tensors="pt")
            if inputs["input_ids"].shape[1] + args.max_new_tokens <= context_limit:
                break
            if len(messages) > 2:
                del messages[1:3]  # Drop the oldest complete user/assistant turn.
            else:
                messages.pop()
                return "Message too long. Please send a shorter message."

        with torch.inference_mode():
            output = model.generate(
                **inputs,
                max_new_tokens=args.max_new_tokens,
                do_sample=True,
                temperature=0.7,
                top_p=0.9,
                repetition_penalty=1.1,
                pad_token_id=tokenizer.eos_token_id,
            )
        answer = tokenizer.decode(output[0, inputs["input_ids"].shape[1]:], skip_special_tokens=True).strip()
        messages.append({"role": "assistant", "content": answer})
        return answer

    if args.prompt is not None:
        print(reply(args.prompt))
        return

    print("Ready. Type /exit to quit or /reset to clear chat history.")
    while True:
        try:
            text = input("You: ").strip()
            if text.lower() in {"/exit", "/quit"}:
                break
            if text.lower() == "/reset":
                messages[:] = [system]
                print("History cleared.")
            elif text:
                print("Assistant:", reply(text))
        except (EOFError, KeyboardInterrupt):
            print()
            break


if __name__ == "__main__":
    main()
