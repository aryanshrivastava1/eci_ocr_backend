# Pramaan OCR Service (Qwen2.5-VL-7B)

Standalone GPU inference service that performs OCR and structured field
extraction on Election Commission of India voter documents.

Extracted verbatim from `ECI_OCR_Backend_MODEL_ARYAN.ipynb`. The OCR
behaviour and API contract are byte-for-byte identical to the notebook —
prompts, blur threshold, preprocessing, two-stage inference, validation,
retry, scoring and response shape are unchanged. Only Colab-specific
plumbing (ngrok, `nest_asyncio`, top-level `await server.serve()`) was
removed, and a shared-secret auth layer was added.

---

## Hardware requirements

| | |
|---|---|
| GPU | **NVIDIA, 24 GB VRAM minimum** |
| Verified on | A100 (Colab) |
| Recommended | L4 (`g6.xlarge`), A10G (`g5.xlarge`), RTX 4090, A100 |
| Disk | ≥ 40 GB (weights ~16 GB + CUDA layers) |
| Driver | CUDA 12.4-capable (see `requirements.txt` to change) |

The model is 7B parameters at BF16 — roughly 16 GB of weights, plus
~1,600 visual tokens and a 3,072-token generation cache.

> **Do not run this below 24 GB VRAM.** `device_map="auto"` will silently
> offload layers to CPU instead of failing, producing correct output at
> 10–50× the latency rather than an obvious error.

CPU-only execution is not viable: each request runs two sequential
generations (four to six on a blurry image).

---

## Environment variables

| Variable | Required | Purpose |
|---|---|---|
| `OCR_SHARED_SECRET` | Recommended | Enables authentication. **Unset = auth disabled.** |
| `HF_HOME` | Recommended | Hugging Face cache root. Set to a persistent volume. Docker default: `/models` |
| `HF_HUB_CACHE` | Optional | Model cache dir. Docker default: `/models/hub` |
| `HF_TOKEN` | Optional | Avoids anonymous Hub rate limits during download |

Supply all of these at run time. Never commit them and never bake them
into the image.

---

## Build the image

```bash
cd ocr_server
docker build -t pramaan-ocr:latest .
```

## Run with GPU

Requires the [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html).

```bash
docker run -d --name pramaan-ocr \
  --gpus all \
  --restart unless-stopped \
  -p 8000:8000 \
  -v /srv/pramaan-models:/models \
  -e OCR_SHARED_SECRET \
  -e HF_TOKEN \
  pramaan-ocr:latest
```

Passing `-e VAR` without a value forwards it from your shell, so secrets
never appear in the command line, shell history, or `docker inspect`
output as literals. Export them from a root-owned `0600` file or your
secret manager first.

The volume at `/models` is important — without it the ~16 GB of weights
re-download on every container restart.

You do **not** need to pre-`chown` the host directory. The container
starts as root only long enough for `docker-entrypoint.sh` to take
ownership of `$HF_HOME`, then drops to the unprivileged `ocr` user
(uid 10001) via `runuser` before Uvicorn starts. If your platform forces
a non-root user with `--user`, the entrypoint detects that and skips the
chown — in that case the mounted volume must already be writable by that
uid.

Startup takes several minutes on a cold cache. The server does not accept
connections until the model is loaded, so a health check that passes means
the service is genuinely ready.

## Run directly for development

```bash
cd ocr_server
python3.11 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

export HF_HOME=/path/to/persistent/cache
uvicorn main:app --host 0.0.0.0 --port 8000
```

Keep `--workers 1`. One Qwen2.5-VL instance owns the GPU; scale with
replicas on additional GPUs, never by raising the worker count.

---

## API

### `GET /health`

Unauthenticated, so orchestrators can probe it. Never touches the GPU.

```bash
curl http://localhost:8000/health
```

```json
{
  "status": "ok",
  "model": "Qwen2.5-VL-7B-Instruct",
  "pipeline": "Two Stage OCR + Field Extraction + Validation"
}
```

### `POST /ocr`

`multipart/form-data`, single file part named **`file`**.

```bash
curl -X POST http://localhost:8000/ocr \
  -H "X-API-Key: $OCR_SHARED_SECRET" \
  -F "file=@voter_card.jpg"
```

When `OCR_SHARED_SECRET` is set, the secret must be presented as either
`X-API-Key: <secret>` or `Authorization: Bearer <secret>`; comparison is
constant-time. A missing or wrong secret returns **401**. While the
variable is unset, no credential is required.

**Success — HTTP 200:**

```json
{
  "success": true,
  "raw_markdown": "{\"voter_name\":\"…\",\"epic_number\":\"…\",\"address\":\"…\",\"serial_number\":\"…\",\"part_number_name\":\"…\",\"constituency\":\"…\",\"state\":\"…\",\"mobile_number\":\"…\"}",
  "validation_status": "valid",
  "validation_issues": [],
  "blur_score": 184.32,
  "image_type": "clear",
  "selected_processing": "original_clear"
}
```

`raw_markdown` is a **JSON string, not a nested object** — the calling
backend parses it with a second `json.loads()`. This is deliberate and
must not be "fixed": it is the contract `app/core/qwen_ocr_client.py`
depends on.

The 8 fields are always all present, empty string when not found:
`voter_name`, `epic_number`, `address`, `serial_number`,
`part_number_name`, `constituency`, `state`, `mobile_number`.

Other keys: `validation_status` is `valid` or `suspicious`;
`validation_issues` lists heuristic warnings; `image_type` is `clear` or
`blurred`; `selected_processing` is `original_clear`, `original_blurred`
or `enhanced_blurred`.

**Failure — HTTP 500:**

```json
{ "success": false, "error": "<message>" }
```

Note that a request whose extraction yields nothing still returns
HTTP 200 with `success: true` and all 8 fields empty — that fallback is
inherited from the notebook and is intentional.

### Connecting the existing backend

Point the backend at this service:

```
QWEN_OCR_API_URL=https://<production-ocr-host>/ocr
```

The path suffix `/ocr` is required. No change to
`app/core/qwen_ocr_client.py` is needed for the request or response
contract — it already sends the `file` field and reads `raw_markdown`.

Two things to plan for:

- **Raise the client timeout.** The client currently uses 120 s. A clear
  image needs two generations; a blurry one needs four to six. The blurry
  path can exceed 120 s even on an A100, which surfaces as a failed job.
  ~300 s is a safer ceiling.
- **Auth is not yet wired up.** Leave `OCR_SHARED_SECRET` unset until the
  client is updated to send the header, or every OCR job will 401.

---

## Model download and caching

First start downloads `Qwen/Qwen2.5-VL-7B-Instruct` (~16 GB) from the
Hugging Face Hub into `HF_HOME`. Point that at a persistent volume, or
pre-warm the cache:

```bash
HF_HOME=/srv/pramaan-models \
  python -c "from huggingface_hub import snapshot_download; \
             snapshot_download('Qwen/Qwen2.5-VL-7B-Instruct')"
```

Anonymous downloads are rate-limited; set `HF_TOKEN` to avoid throttling.
The model is publicly available, so a token is not otherwise required.

---

## Production security requirements

The notebook exposed this service publicly with no authentication. Before
this reaches production:

1. **Set `OCR_SHARED_SECRET`** to a long random value from a secret
   manager, and configure the caller to send it. Generate one with
   `openssl rand -hex 32`.
2. **Terminate TLS in front of the service** (nginx, Caddy, or an ALB).
   Uvicorn here serves plain HTTP on port 8000 — never expose that port
   directly to the internet.
3. **Restrict network access** to the backend's egress IP via security
   group or firewall. Do not leave port 8000 open to `0.0.0.0/0`.
4. **Rotate the ngrok token** that is hardcoded in the Colab notebook.
   It is not used here and was not copied into this service, but it is
   still live wherever that notebook exists.
5. **Add a request size limit and rate limiting** at the reverse proxy.
   The service itself does not cap upload size, and one 7B model serving
   one request at a time makes it trivially easy to saturate.
6. **Keep the notebook out of Git.** `*.ipynb` is gitignored at the repo
   root for exactly this reason.

### No secrets in this repository

Nothing in `ocr_server/` contains a credential, and nothing should. All
secrets arrive through the environment at run time. `.dockerignore`
excludes `.env`, key material, notebooks and cloud-credential files from
the build context, and `.env` is gitignored at the repo root.

Do not paste real tokens into this README, into `Dockerfile` `ENV` lines,
or into example commands — the examples above deliberately reference
variables (`$OCR_SHARED_SECRET`) rather than values.
