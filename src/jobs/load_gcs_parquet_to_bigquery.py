import os
import logging
from google.cloud import bigquery

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

REPORTS_MAPPING = {
    "membros_export": "raw_members",
    "avaliacao_de_habilidades_export": "raw_skill_assessments",
    "catalogo_de_conteudo_export": "raw_content_catalog",
    "historico_da_equipe_export": "raw_team_history",
    "resumo_export": "raw_summary",
    "resumo_por_certificacao_export": "raw_certifications",
    "resumo_por_curso_export": "raw_course_activity",
    "resumo_por_programa_export": "raw_program_activity",
    "resumo_por_projeto_export": "raw_project_activity",
    "tempo_no_aprendizado_export": "raw_time_spent",
}


def run():
    """Carrega os arquivos Parquet do Cloud Storage para o BigQuery."""

    project_id = os.environ.get("GCP_PROJECT")
    bucket_name = os.environ.get("RAW_BUCKET")
    dataset_id = os.environ.get("BQ_RAW_DATASET", "raw")

    if not project_id or not bucket_name:
        raise ValueError("As variáveis GCP_PROJECT e RAW_BUCKET devem estar definidas.")

    client = bigquery.Client(project=project_id)

    job_config = bigquery.LoadJobConfig(
        source_format=bigquery.SourceFormat.PARQUET,
        write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
    )

    logger.info("Iniciando carga dos arquivos para o BigQuery.")

    total = len(REPORTS_MAPPING)

    for index, (source_folder, table_name) in enumerate(
        REPORTS_MAPPING.items(), start=1
    ):
        gcs_uri = f"gs://{bucket_name}/datacamp/raw/{source_folder}/*.parquet"
        table_id = f"{project_id}.{dataset_id}.{table_name}"

        logger.info("[%d/%d] Carregando %s", index, total, table_name)

        try:
            load_job = client.load_table_from_uri(
                gcs_uri,
                table_id,
                job_config=job_config,
            )

            load_job.result()

            table = client.get_table(table_id)

            logger.info(
                "Tabela %s carregada com %d linhas.",
                table_id,
                table.num_rows,
            )

        except Exception:
            logger.exception("Erro ao carregar a tabela %s.", table_name)
            raise

    logger.info("Carga concluída com sucesso.")
