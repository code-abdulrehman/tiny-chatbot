# Gateway browser client

This browser app sends chat requests to the model gateway. Set the gateway URL, API key, and approved model in Settings. There is no browser-side inference or model download.

Saved chats stay in this browser's local storage; private chats stay in tab memory. Prompts and replies travel through the gateway to the selected model host. The API key is kept in tab session storage and should only be used for development until browser session authentication is implemented.

Run with Node.js 20.19+:

```bash
npm install
npm run dev
```

Build with `npm run build` and serve `dist/` as a static site. The gateway currently needs a same-origin proxy or an explicit allowed-origin policy for browser requests from a separate origin. Run checks with `npm test`.
