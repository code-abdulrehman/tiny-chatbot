import { pipeline, TextStreamer, InterruptableStoppingCriteria } from '@huggingface/transformers';

// The ONNX weights are fetched from Hugging Face by each browser and cached there.
const MODEL = 'onnx-community/Qwen2.5-0.5B-Instruct';
const SYSTEM = 'You are Tiny Chat, a concise helpful assistant. Answer in the language of the user. Say when you are unsure.';
let generator;
let loading;
let device;
let stopping;
let currentId;
const cancelled = new Set();

async function loadModel() {
  if (generator) return generator;
  if (loading) return loading;
  let adapter = null;
  try { adapter = await navigator.gpu?.requestAdapter(); } catch { /* CPU fallback below */ }
  device = adapter ? 'webgpu' : 'wasm';
  const createPipeline = (runtime) => {
    const dtype = runtime === 'webgpu' ? 'q4f16' : 'q8';
    postMessage({ type: 'loading', device: runtime, dtype });
    return pipeline('text-generation', MODEL, {
      device: runtime,
      dtype,
      progress_callback: (progress) => {
        if (progress.status === 'progress' && progress.total) {
          postMessage({ type: 'download', percent: Math.round(progress.progress || progress.loaded / progress.total * 100) });
        }
      },
    });
  };
  loading = createPipeline(device);
  try {
    try {
      generator = await loading;
    } catch (error) {
      if (device !== 'webgpu') throw error;
      device = 'wasm';
      loading = createPipeline(device);
      generator = await loading;
    }
    postMessage({ type: 'ready', device, dtype: device === 'webgpu' ? 'q4f16' : 'q8' });
    return generator;
  } finally {
    loading = null;
  }
}

function answerText(output) {
  const result = output?.[0]?.generated_text;
  if (typeof result === 'string') return result;
  if (Array.isArray(result)) return result.at(-1)?.content || '';
  return '';
}

async function generate({ id, messages, maxNewTokens, contextMessages, title = false }) {
  currentId = id;
  const model = await loadModel();
  if (cancelled.delete(id)) {
    postMessage({ type: 'done', id, text: '', truncated: false });
    currentId = null;
    return;
  }
  stopping = new InterruptableStoppingCriteria();
  let streamed = '';
  let tokenCount = 0;
  const streamer = new TextStreamer(model.tokenizer, {
    skip_prompt: true,
    skip_special_tokens: true,
    callback_function: (text) => {
      streamed += text;
      postMessage({ type: 'token', id, text });
    },
    token_callback_function: () => { tokenCount += 1; },
  });
  const history = title
    ? [{ role: 'system', content: 'Write a short 2 to 5 word title for this conversation. Output only the title.' },
      { role: 'user', content: messages.slice(0, 2).map((m) => `${m.role}: ${m.content}`).join('\n') }]
    : [{ role: 'system', content: SYSTEM }, ...messages.slice(-contextMessages)];
  try {
    const output = await model(history, {
      max_new_tokens: title ? 16 : maxNewTokens,
      do_sample: false,
      streamer,
      stopping_criteria: [stopping],
    });
    postMessage({ type: 'done', id, text: answerText(output) || streamed, truncated: tokenCount >= (title ? 16 : maxNewTokens) });
  } catch (error) {
    postMessage({ type: 'error', id, message: error?.message || String(error) });
  } finally {
    stopping = null;
    currentId = null;
  }
}

onmessage = async ({ data }) => {
  if (data.type === 'stop') {
    if (stopping) stopping.interrupt();
    else if (currentId) cancelled.add(currentId);
    return;
  }
  if (data.type !== 'generate') return;
  try {
    await generate(data);
  } catch (error) {
    currentId = null;
    cancelled.delete(data.id);
    postMessage({ type: 'error', id: data.id, message: error?.message || String(error) });
  }
};
