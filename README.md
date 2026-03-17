# everest

## KAD Recorder

Install tooling:

```bash
poetry install
poetry run playwright install chromium
```

Start the recorder:

```bash
poetry run record-kad --output recordings/kad_web.jsonl
```

Useful modes:

```bash
poetry run record-kad --output recordings/kad_web.jsonl
poetry run record-kad --fresh-profile --output recordings/kad_web_fresh.jsonl
poetry run record-kad --channel chrome --output recordings/kad_web_chrome.jsonl
poetry run record-kad --all-domains --channel chrome --output recordings/kad_web_full.jsonl
```

It will open `https://kad.arbitr.ru`, record requests, responses, failed requests, console errors, page errors, websocket traffic, cookies, storage snapshots, and save response bodies into a sibling `_bodies` directory. Press Enter in the terminal to stop.
