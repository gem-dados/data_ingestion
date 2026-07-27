"""Entrypoint HTTP do servico Cloud Run.

Cloud Run espera um servidor HTTP escutando em $PORT. Aqui um Flask minimo
expoe /healthz e /run/<job> para disparar jobs de ingestao.
"""

from __future__ import annotations

import os

from flask import Flask, jsonify

from jobs import upload_parquet_to_gcs, load_gcs_parquet_to_bigquery

app = Flask(__name__)

# Registro simples de jobs disponiveis.
JOBS = {
    "upload_gcs": upload_parquet_to_gcs.run,
    "load_bq": load_gcs_parquet_to_bigquery.run,
}


@app.get("/healthz")
def healthz():
    return jsonify(status="ok")


@app.post("/run/<job_name>")
def run_job(job_name: str):
    job = JOBS.get(job_name)
    if job is None:
        return jsonify(error=f"job desconhecido: {job_name}"), 404
    job()
    return jsonify(status="done", job=job_name)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "8080")))
