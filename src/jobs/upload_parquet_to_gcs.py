"""Job de Desenvolver script de upload para enviar os arquivos processados
para a camada RAW do Storage.


"""


from __future__ import annotations


import logging
import os
import pathlib
from google.cloud import storage  # type: ignore
from src.jobs.identify_datacamp_csvs import run as ingestao_e_conversao

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("ingestion")


def upload_arquivo_para_gcs(project: str, bucket_name: str, caminho_local: pathlib.Path, rota_na_nuvem: str) -> None:
    """Conecta ao Google Cloud Storage e faz o upload de um arquivo local."""
    try:
        # Inicializa o cliente do GCS usando o projeto injetado
        client = storage.Client(project=project)
        bucket = client.bucket(bucket_name)
       
        # Cria o "ponteiro" do objeto dentro do bucket na nuvem
        blob = bucket.blob(rota_na_nuvem)
       
        log.info("Enviando %s para gs://%s/%s ...", caminho_local.name, bucket_name, rota_na_nuvem)
       
        # Faz o upload do arquivo binário (.parquet)
        blob.upload_from_filename(str(caminho_local))
       
        log.info("Upload concluido com sucesso!")
       
    except Exception as e:
        log.error("Falha ao enviar o arquivo %s para o GCS: %s", caminho_local.name, str(e))
        raise e


def run() -> None:
    log.info("Iniciando o Job de Ingestão e Upload para o Google Cloud Storage")
    
    # 1. Executar função de Ingestão e Conversão
    log.info("Executando a etapa previa de ingestao e conversao para Parquet...") 
    ingestao_e_conversao()

    # 2. Variaveis de ambiente padrao (injetadas pelo Terraform)
    project = os.environ.get("GCP_PROJECT", "gem-dados-lake-stg")          
    raw_bucket = os.environ.get("RAW_BUCKET", "gem-dados-lake-stg-raw")
   
    # 3. Se houver arquivos legados em disco local, processa como utilitario
    pasta_processados = pathlib.Path("dados_processados")
    if pasta_processados.exists():
        arquivos_parquet = list(pasta_processados.glob("*.parquet"))
        for arquivo in arquivos_parquet:
            nome_relatorio = arquivo.stem
            rota_na_nuvem = f"datacamp/raw/{nome_relatorio}/{arquivo.name}"
            upload_arquivo_para_gcs(project, raw_bucket, arquivo, rota_na_nuvem)
        log.info("Uploads locais complementares processados.")
    else:
        log.info("Ingestao direta para o GCS concluida com sucesso via identify_datacamp_csvs.")


if __name__ == "__main__":
    run()