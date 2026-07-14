# Kanuni

Kanuni (Swahili: "rule / regulation") is a production-grade Retrieval-Augmented
Generation system for asking natural-language questions about Bank of
Tanzania financial regulations and receiving cited, versioned,
confidence-gated answers.

> **Status:** Phase 0 (skeleton & spine) — see [PROJECT_SPEC.md](PROJECT_SPEC.md)
> for the full build specification and [docs/](docs/) for architecture notes.
> This README will be filled out per §16 of the spec as later phases land.

## Quickstart

```bash
make setup   # install Python (uv) and JS (bun) dependencies
make dev     # docker compose up: postgres, api, ingestion worker, web
```

Once running:

- API health: `curl http://localhost:8000/healthz`
- API readiness: `curl http://localhost:8000/readyz`
- Frontend: http://localhost:3000

## Repository layout

See [PROJECT_SPEC.md § 3](PROJECT_SPEC.md#3-repository-structure-monorepo)
for the full monorepo layout and the rationale behind it.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md).

## Security

See [SECURITY.md](SECURITY.md) for the vulnerability disclosure policy.

## License

[MIT](LICENSE)
