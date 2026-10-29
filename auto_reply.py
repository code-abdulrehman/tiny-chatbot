"""Continue token-limited generations until EOS, context exhaustion, or no progress."""


def complete_reply(engine, history, *, max_new_tokens, context_tokens, continuing=False, sample=False, status=None):
    status = status if status is not None else {}
    status.update(truncated=False, pause_reason=None)
    base = history[:-1] if continuing else history
    answer = history[-1]['content'] if continuing else ''
    continuing_now = continuing
    while True:
        request = base + [{'role': 'assistant', 'content': answer}] if continuing_now else base
        step = {}
        before = answer
        stream = engine.stream(request, max_new_tokens=max_new_tokens, context_tokens=context_tokens,
                               sample=sample, continue_reply=continuing_now, generation_status=step)
        try:
            try:
                for chunk in stream:
                    if chunk:
                        answer += chunk
                        yield chunk
            except ValueError as exc:
                if continuing_now and answer and 'context' in str(exc).lower():
                    status.update(truncated=True, pause_reason='Context is full. Increase context length in Settings, then Continue.')
                    return
                raise
        finally:
            close = getattr(stream, 'close', None)
            if close:
                close()
        if not step.get('truncated'):
            status.update(truncated=False, pause_reason=None)
            return
        if answer == before:
            status.update(truncated=True, pause_reason='The model made no progress. Try Retry or a different question.')
            return
        status['truncated'] = True
        continuing_now = True
