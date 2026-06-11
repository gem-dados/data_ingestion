"""Job de exemplo de ingestao.

Le config do ambiente (injetada pelo Cloud Run / Terraform) e grava um
arquivo na landing zone (bucket raw). Use como molde para novos jobs.

Boas praticas demonstradas:
  - NENHUM segredo no codigo: tudo vem de env vars / Secret Manager
  - logging estruturado simples
  - funcao pura testavel + entrypoint fino
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("ingestion")


def build_payload(env: str) -> dict:
    """Monta um payload de exemplo (parte pura, facil de testar)."""
    return {
        "env": env,
        "ingested_at": datetime.now(timezone.utc).isoformat(),
        "source": "example",
        "records": [{"id": 1, "value": "hello-lake"}],
    }


def run() -> None:
    project = os.environ["GCP_PROJECT"]          # injetado pelo Terraform
    env = os.environ.get("ENVIRONMENT", "stg")
    raw_bucket = os.environ["RAW_BUCKET"]

    payload = build_payload(env)
    object_path = f"example/{payload['ingested_at']}.json"

    log.info("escrevendo gs://%s/%s (projeto=%s)", raw_bucket, object_path, project)

    # Import tardio: mantem o modulo importavel em testes sem credenciais GCP.
    from google.cloud import storage  # type: ignore

    client = storage.Client(project=project)
    bucket = client.bucket(raw_bucket)
    bucket.blob(object_path).upload_from_string(
        json.dumps(payload), content_type="application/json"
    )
    log.info("ok: %d registro(s) gravado(s)", len(payload["records"]))


if __name__ == "__main__":
    run()
