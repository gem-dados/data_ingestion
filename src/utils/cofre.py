import os
import io
import pandas as pd
from google.cloud import storage

def deduplicate_dataframe(df: pd.DataFrame, primary_key: str, order_by_col: str = None) -> pd.DataFrame:
    """
    Deduplica o DataFrame em memória.
    Mantém o registro mais recente com base em uma coluna temporal.
    """
    df_clean = df.copy()
    if order_by_col and order_by_col in df_clean.columns:
        df_clean[order_by_col] = pd.to_datetime(df_clean[order_by_col])
        df_clean = df_clean.sort_values(by=order_by_col, ascending=True)
        
    return df_clean.drop_duplicates(subset=[primary_key], keep='last')


def sync_vault_table(
    df_novos: pd.DataFrame, 
    bucket_name: str, 
    vault_path: str = "vault/cofre_anonimizacao.parquet",
    col_email: str = "email_aluno",
    col_hash: str = "hash_anonimizado"
) -> None:
    """
    Realiza o Upsert (Merge) na tabela Cofre no GCS sem duplicar alunos existentes.
    """
    project = os.getenv("GCP_PROJECT", "gem-dados-lake-stg")
    client = storage.Client(project=project)
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(vault_path)
    
    # Extrai novos mapeamentos
    novos_mapeamentos = df_novos[[col_email, col_hash]].dropna().copy()
    
    # Se a tabela Cofre já existir no GCS, baixa e une
    if blob.exists():
        buffer = io.BytesIO()
        blob.download_to_file(buffer)
        buffer.seek(0)
        cofre_existente = pd.read_parquet(buffer)
        cofre_unificado = pd.concat([cofre_existente, novos_mapeamentos], ignore_index=True)
    else:
        cofre_unificado = novos_mapeamentos

    # Deduplica mantendo a primeira ocorrência do e-mail
    cofre_final = cofre_unificado.drop_duplicates(subset=[col_email], keep='first')
    
    # Salva Parquet atualizado de volta no GCS
    out_buffer = io.BytesIO()
    cofre_final.to_parquet(out_buffer, index=False, engine='pyarrow')
    out_buffer.seek(0)
    blob.upload_from_file(out_buffer, content_type='application/octet-stream')
    
    print(f"🔒 Tabela Cofre sincronizada! Total de alunos mapeados: {len(cofre_final)}")