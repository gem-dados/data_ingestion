SHELL := /bin/bash
.SHELLFLAGS := -eu -o pipefail -c

# Usa o executável Python da .venv se existir, senão usa o python3 padrão
PYTHON := .venv/bin/python3

.PHONY: help check-env ingest upload_gcs load_bq deduplicate run

help:
	@echo "Comandos disponíveis:"
	@echo "  make run          - Executa o pipeline completo (Ingestão -> Upload GCS -> Carga BQ -> Deduplicação)"
	@echo "  make ingest       - Ingestão, classificação e anonimização dos CSVs locais"
	@echo "  make upload_gcs   - Upload dos arquivos Parquet para o Google Cloud Storage"
	@echo "  make load_bq      - Carga dos Parquets do GCS para o BigQuery"
	@echo "  make deduplicate  - Atualização da tabela Cofre sem duplicatas"

# Verifica se os arquivos e variáveis necessários existem antes de rodar
check-env:
	@test -f .env || (echo "ERRO: Arquivo .env não encontrado!" && exit 1)
	@test -f client_secret.json || (echo "ERRO: Arquivo client_secret.json não encontrado na raiz!" && exit 1)

ingest: check-env
	@echo "==> [1/4] Ingestão e Anonimização (identify_datacamp_csvs)..."
	$(PYTHON) -m src.jobs.identify_datacamp_csvs

upload_gcs: check-env
	@echo "==> [2/4] Upload Parquet para o GCS (upload_parquet_to_gcs)..."
	$(PYTHON) -m src.jobs.upload_parquet_to_gcs

load_bq: check-env
	@echo "==> [3/4] Carga no BigQuery (load_gcs_parquet_to_bigquery)..."
	$(PYTHON) -m src.jobs.load_gcs_parquet_to_bigquery

deduplicate: check-env
	@echo "==> [4/4] Atualização da Tabela Cofre sem duplicatas (rotina_sem_duplicatas_job)..."
	$(PYTHON) -m src.jobs.rotina_sem_duplicatas_job

# Executa todas as etapas em cadeia na ordem estrita de dependência
run: ingest upload_gcs load_bq deduplicate
	@echo "==> Pipeline completo executado com sucesso!"