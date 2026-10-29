# Tiny Chat in the browser

This is a separate browser-only edition of Tiny Chat. The existing Streamlit app in the parent directory still works. Model inference runs in a Web Worker on the visitor's device. The model is downloaded from Hugging Face to the browser cache; no model weights are committed to Git. Saved chats and settings use that browser's `localStorage`. Private chats stay in memory until the tab is closed or another chat is opened. No chats are sent to the app host, but prompts and replies are processed by the model in the browser. The browser contacts Hugging Face to download model files.

## Run locally

Install Node.js 20.19+ and npm, then:

```bash
cd browser
./run.sh
```

Open the local address Vite prints (usually `http://127.0.0.1:5173`). On the first message, the browser downloads `onnx-community/Qwen2.5-0.5B-Instruct` ONNX weights. WebGPU uses q4f16 (~483 MB); devices without WebGPU fall back to WASM q8 (~512 MB). The first download takes time. Browser storage may evict cached model files, requiring another download. CPU generation can be slow, particularly on phones.

## Build and host

```bash
cd browser
npm install
npm run build
```

Publish only `browser/dist/` to a static host such as GitHub Pages, Cloudflare Pages, or Netlify. Use `browser` as the project root if your host builds from the repository, with build command `npm run build` and output directory `dist`. No Python, Streamlit server, SQLite database, model upload, or API key is needed for this edition. Serve it over HTTPS for WebGPU; localhost also works during development. Streamlit Community Cloud is intended for Python Streamlit apps, so a static host is the simpler fit for this browser edition.

Saved chats are specific to each browser and can disappear if the user clears site data. There is no cross-device sync or account system. Model answers can be inaccurate. Retry replaces the latest reply; Continue asks the model to extend a token-limited answer. The wording may overlap because continuation is a new inference call.

## Test

```bash
npm test
```
