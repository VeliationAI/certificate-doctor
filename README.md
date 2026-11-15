# Certificate Doctor

**Is this marksheet forged?**

Upload a certificate or marksheet (image or PDF). Certificate Doctor runs five forensic checks and returns one score out of 100 — verdict, highlighted tamper regions, explanations, markdown + JSON export. Offline-capable core. No GPU. MIT.

Built by [Veliation AI](https://github.com/VeliationAI) · Doctor family product.

## Rubric

| Check | Weight |
|---|---:|
| Error Level Analysis (ELA) | 30 |
| Text / font consistency | 25 |
| Metadata | 15 |
| Copy-move detection | 15 |
| Logic checks | 15 |

### Verdicts

| Score | Verdict |
|---|---|
| ≥ 75 | Likely Genuine |
| 50–74 | Needs Review |
| < 50 | Likely Tampered |

## Honest scope

- **Cannot** verify against university databases
- **Not** court-proof — screening tool with evidence
- Heavy compression can **false-positive**
- Professional forgeries may **slip through**

## Quick start (CLI)

```bash
pip install -e .
certificate-doctor scan samples/genuine_marksheet.jpg
certificate-doctor scan samples/tampered_marksheet.jpg --export ./out
```

## Web app

```bash
pip install -e .
uvicorn web.app:app --reload --port 8000
```

Open http://localhost:8000 — drop a file, or tap a synthetic sample. Heatmap + score appear automatically.

## Demo story (synthetic, no real PII)

| Sample | Expected score |
|---|---|
| `samples/genuine_marksheet.jpg` | ~90s · Likely Genuine |
| `samples/tampered_marksheet.jpg` | ~30s · Likely Tampered (ELA + logic + metadata) |

Regenerate samples:

```bash
python scripts/generate_samples.py
```

## Optional OCR

Text/font and OCR-backed logic improve with [Tesseract](https://github.com/tesseract-ocr/tesseract):

```bash
pip install pytesseract
# plus system Tesseract binary
```

Without Tesseract, those checks **degrade gracefully**; ELA, metadata, copy-move, and embedded logic payloads still run (demo samples include a logic payload).

## v0.1

- Image + PDF (first page)
- ELA heatmap overlay
- Metadata / copy-move / logic heuristics
- Typer CLI + FastAPI UI
- Markdown + JSON export

## Stack

Python · OpenCV · Pillow · Tesseract (optional) · FastAPI · Typer · MIT

## License

MIT © Veliation AI
