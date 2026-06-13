"""Job de exemplo de ingestao.

Le config do ambiente (injetada pelo Cloud Run / Terraform), grava o arquivo
cru na landing zone (bucket raw) E carrega os registros na tabela `raw.example`
do BigQuery — que e a fonte declarada no Dataform (data_models).

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
        "records": [
            {"id": 1, "value": "hello-lake"},
            {"id": 2, "value": "gem-dados"},
        ],
    }


def _write_landing(project: str, bucket: str, object_path: str, payload: dict) -> None:
    """Grava o JSON cru na landing zone (bucket GCS)."""
    from google.cloud import storage  # type: ignore

    client = storage.Client(project=project)
    client.bucket(bucket).blob(object_path).upload_from_string(
        json.dumps(payload), content_type="application/json"
    )
    log.info("landing: gs://%s/%s", bucket, object_path)


def _load_raw(project: str, dataset: str, table: str, records: list[dict]) -> None:
    """Carrega os registros na tabela raw.<table> do BigQuery (cria se preciso)."""
    from google.cloud import bigquery  # type: ignore

    client = bigquery.Client(project=project)
    table_id = f"{project}.{dataset}.{table}"

    job_config = bigquery.LoadJobConfig(
        autodetect=True,
        write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
        source_format=bigquery.SourceFormat.NEWLINE_DELIMITED_JSON,
    )
    client.load_table_from_json(records, table_id, job_config=job_config).result()
    log.info("raw: %s (%d registros)", table_id, len(records))


def run() -> None:
    project = os.environ["GCP_PROJECT"]          # injetado pelo Terraform
    env = os.environ.get("ENVIRONMENT", "stg")
    raw_bucket = os.environ["RAW_BUCKET"]
    bq_dataset = os.environ.get("BQ_DATASET", "raw")

    payload = build_payload(env)
    object_path = f"example/{payload['ingested_at']}.json"

    _write_landing(project, raw_bucket, object_path, payload)
    _load_raw(project, bq_dataset, "example", payload["records"])
    log.info("ingestao concluida")


if __name__ == "__main__":
    run()
