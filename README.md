<h1 align="center">
  <img src="https://raw.githubusercontent.com/antonillos/pm2insomnia/main/assets/post-insomnia-icon.svg" alt="pm2insomnia icon" width="180" /><br />
  pm2insomnia
</h1>

<p align="center">
  <a href="https://github.com/antonillos/pm2insomnia/actions/workflows/tests.yml">
    <img src="https://github.com/antonillos/pm2insomnia/actions/workflows/tests.yml/badge.svg" alt="Tests" />
  </a>
  <img src="https://img.shields.io/badge/python-3.11%2B-blue" alt="Python 3.11+" />
  <img src="https://img.shields.io/badge/code%20style-ruff-261230?logo=ruff&logoColor=white" alt="Code style: Ruff" />
  <a href="LICENSE">
    <img src="https://img.shields.io/badge/license-MIT-lightgrey" alt="MIT License" />
  </a>
</p>

<h3 align="center">
  Move your Postman collections to Insomnia in seconds — no manual work.
</h3>

<p align="center">
  <a href="#install">Install</a> •
  <a href="#usage">Usage</a> •
  <a href="#what-gets-converted">What gets converted</a> •
  <a href="#license">License</a>
</p>

---

If your team exports collections from Postman but you prefer working in Insomnia, `pm2insomnia` does the conversion for you. Drop in a Postman export, get an Insomnia file ready to import — folders, requests, environments, auth, and examples included.

## Install

The easiest way is with [pipx](https://pipx.pypa.io), which installs the tool globally and keeps it isolated from your Python environment:

```bash
pipx install pm2insomnia
```

That's it. The `pm2insomnia` command is now available anywhere in your terminal.

> **Don't have pipx?** Install it first:
> ```bash
> pip install pipx
> ```

## Usage

### Convert a collection

```bash
pm2insomnia convert --input my-collection.postman.json
```

This creates `my-collection.insomnia.json` in the same folder. Open Insomnia, go to **Import**, and select that file.

Want to include your Postman environments too?

```bash
pm2insomnia convert \
  --input my-collection.postman.json \
  --environment my-environments.json
```

### Export a versioned bundle

If you want to store the collection and API docs together in a repository:

```bash
pm2insomnia bundle \
  --input my-api-1.9.1.postman.json \
  --workspace-name "My API" \
  --output-dir exports/
```

This generates a tidy folder structure:

```
exports/
  collections/my-api/1.9.1/my-api.insomnia.json
  api-docs/my-api/1.9.1/README.md
```

You can also attach an OpenAPI spec:

```bash
pm2insomnia bundle \
  --input my-api-1.9.1.postman.json \
  --workspace-name "My API" \
  --spec openapi.yaml \
  --environment environments.zip \
  --output-dir exports/
```

### Importing in Insomnia

1. Open Insomnia → **Import**
2. Select the `.insomnia.json` file
3. Done — your collection, environments, and examples are ready

## Options

| Flag | What it does |
|------|-------------|
| `--input` | Path to your Postman collection JSON |
| `--environment` | Postman environment file (`.json` or `.zip`). Repeat for multiple files |
| `--output` | Where to write the Insomnia file (default: same folder as input) |
| `--output-dir` | Write the output into a specific directory |
| `--workspace-name` | Override the workspace name shown in Insomnia |
| `--pretty` | Format the JSON output so it's readable |
| `--strict` | Fail with exit code `2` if anything couldn't be converted |

## What gets converted

✅ Folders and subfolders  
✅ Requests — method, URL, headers, query params  
✅ Request and folder descriptions  
✅ Body — raw, form, and URL-encoded  
✅ Path variables  
✅ Bearer auth  
✅ Saved response examples  
✅ Collection variables → Insomnia base environment  
✅ Postman environments → Insomnia sub-environments  

## What doesn't convert

These Postman features have no direct equivalent in Insomnia and are skipped. The tool will warn you when it encounters them:

- Pre-request and test scripts
- Auth types other than Bearer
- GraphQL body mode
- Variable resolution (placeholders are kept as-is)

## License

MIT. See [LICENSE](LICENSE).
