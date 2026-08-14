import os
import io
import pandas as pd
from google.cloud import storage

from utils.cofre import deduplicate_dataframe, sync_vault_table
from utils.crypto import gerar_user_id

def run():
    # Lê as variáveis de ambiente com fallback para os nomes do projeto
    project = os.getenv("GCP_PROJECT", "gem-dados-lake-stg")
    bucket_name = os.getenv("RAW_BUCKET", "gem-dados-lake-stg-raw")
    
    if not bucket_name:
        raise ValueError("A variável RAW_BUCKET não foi configurada no ambiente!")

    print(f"🚀 Iniciando Job de Deduplicação e Cofre no Bucket: {bucket_name}")
    
    raw_blob_path = "landing/alunos_datacamp.csv"
    
    # Passa o project explicitamente para o cliente do GCS (evita o OSError)
    client = storage.Client(project=project)
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(raw_blob_path)
    
    if not blob.exists():
        print(f"⚠️ Arquivo {raw_blob_path} não encontrado no bucket. Pulando execução.")
        return {"status": "skipped", "reason": "file_not_found"}

    # 1. Leitura do arquivo CSV
    content = blob.download_as_bytes()
    df_raw = pd.read_csv(io.BytesIO(content))

    # 2. Criptografia / Hash LGPD
    df_raw['hash_anonimizado'] = df_raw['email_aluno'].fillna("").astype(str).apply(gerar_user_id)

    # 3. Deduplicação do dataset em memória
    df_clean = deduplicate_dataframe(df_raw, primary_key='email_aluno', order_by_col='updated_at')

    # 4. Upsert na tabela Cofre
    sync_vault_table(df_clean, bucket_name=bucket_name)

    # 5. Salva Parquet limpo na camada Silver
    df_silver = df_clean.drop(columns=['email_aluno'])
    out_buffer = io.BytesIO()
    df_silver.to_parquet(out_buffer, index=False, engine='pyarrow')
    out_buffer.seek(0)
    
    silver_blob = bucket.blob("silver/alunos/alunos_deduplicados.parquet")
    silver_blob.upload_from_file(out_buffer)

    print("🎉 Processamento concluído com sucesso!")
    return {"status": "success", "rows": len(df_silver)}


if __name__ == "__main__":
    run()