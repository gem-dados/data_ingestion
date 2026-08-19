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

    # 2. Variáveis de ambiente padrão (injetadas pelo Terraform)
    project = os.environ.get("GCP_PROJECT", "projeto-local")          
    raw_bucket = os.environ.get("RAW_BUCKET", "bucket-local")
   
    # 3. Pasta onde estão os arquivos Parquet que gerados
    pasta_processados = pathlib.Path("dados_processados")
   
    if not pasta_processados.exists():
        log.error("A pasta '%s' nao existe. Certifique-se de rodar 'identify_datacamp_csvs.py' primeiro.", pasta_processados)
        return


    # 4. Loop para escanear a pasta local e enviar cada arquivo .parquet encontrado
    arquivos_parquet = list(pasta_processados.glob("*.parquet"))
   
    if not arquivos_parquet:
        log.warning("Nenhum arquivo .parquet encontrado para upload em '%s'.", pasta_processados)
        return


    for arquivo in arquivos_parquet:
        # Define a estrutura de pastas que o arquivo terá dentro da nuvem (Landing Zone)
        # Ex: datacamp/raw/tempo_no_aprendizado.parquet
# Se o arquivo for "usuarios_registrados.parquet", o .stem captura apenas "usuarios_registrados"
        nome_relatorio = arquivo.stem
        rota_na_nuvem = f"datacamp/raw/{nome_relatorio}/{arquivo.name}"


       
        upload_arquivo_para_gcs(project, raw_bucket, arquivo, rota_na_nuvem)


    log.info("Todos os uploads foram processados.")


if __name__ == "__main__":
    run()