# Public GitHub Cutover

This workspace is a working studio, not yet a clean public repo. Before pushing `aiButler.me` publicly, extract or remove the material that does not belong in an open-source product repository.

## Keep

- `aibutler-core/`
- `desktop/`
- `mobile/`
- `bridge/`
- `landing/`
- `docs/`
- `scripts/`
- `README.md`
- `CONTRIBUTING.md`
- `SECURITY.md`
- `LICENSE`
- `.env.example`

## Review Before Publishing

- `AI Clone/`
- `Public Speaking aiButler.me/`
- `Voice Assistant/`
- `Sales/`
- `Website/`
- `AShoulderTo.com/`
- `Youtube Downloader app/`
- `My Ai Butler and Me.scriv/`
- loose `.docx`, `.pptx`, `.mov`, `.wav`, `.mp3`, `.zip` artifacts in repo root

These may contain:

- personal media
- proprietary decks
- research scraps
- unrelated experiments
- publishable ideas that do not belong in the open-source product repo

## Cutover Rule

Do not publish this workspace wholesale. Create a clean public repo root from the product folders, then selectively re-add only the documents and assets that are intentional public artifacts.

## Suggested Public Repo Shape

```text
aiButler.me/
├── aibutler-core/
├── desktop/
├── mobile/
├── bridge/
├── landing/
├── docs/
├── scripts/
├── README.md
├── CONTRIBUTING.md
├── SECURITY.md
├── LICENSE
└── .env.example
```

## Final Pre-Push Checks

1. Search for hard-coded secrets, tokens, emails, and API keys.
2. Confirm `node_modules/`, build artifacts, and local runtime state are ignored.
3. Remove personal training media unless it is intentionally public.
4. Make sure README and landing copy match the actual state of the product.
5. Run the local verification suite before the first public commit.
