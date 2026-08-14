"""Job de identificacao e ingestao de relatorios DataCamp.

Faz a ingestão dos CSVs disponibilizados no Google Drive via Google API (com conta de serviço).
Ler dinamicamente o cabeçalho dos arquivos e classificar os 10 tipos de relatórios.

"""

from __future__ import annotations

import csv
import io
import json
import logging
import os
import pathlib
import pickle
from dotenv import load_dotenv 
from utils.crypto import gerar_user_id      
from datetime import datetime, timezone

# Google APIs
from google.auth import default
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from google.cloud import storage  # type: ignore
from google_auth_oauthlib.flow import InstalledAppFlow  # Adicionado para o fluxo do navegador
from google.auth.transport.requests import Request  # Adicionado para renovar o token expirado
import pandas as pd

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("ingestion")

MAPEAMENTO_RELATORIOS = {
    "tempo_no_aprendizado": ["firstname", "lastname", "email", "alltypes", "courses(classic)", "courses(ai native)", "courses", "assessments", "projects", "practices"],
    "resumo_por_projeto": ["FirstName", "LastName", "UserEmail", "Teams", "ProjectId", "ProjectName", "Technology", "StartedAt", "CompletedAt"],
    "resumo_por_programa": ["FirstName", "LastName", "UserEmail", "Teams", "TrackId", "TrackVersionId", "TrackTitle", "Technology", "StartedAt", "CompletedAt", "% XP Earned", "Hours Spent", "NumCourses", "NumCoursesCompleted", "NumChapters", "NumChaptersCompleted", "NumProjects", "NumProjectsCompleted", "NumAssessments", "NumAssessmentsCompleted"],
    "resumo_por_curso": ["FirstName", "LastName", "UserEmail", "UserName", "Teams", "JoinedGroup", "LeftGroup", "CourseId", "CourseName", "Technology", "StartedCourse", "FinishedCourse", "SkippedCourse", "LastVisitedCourse", "CompletedCourseExercises", "CourseCompletionRate", "CourseStatus", "TotalCourseXPEarned", "TotalCourseXPAvailable", "XPScore", "CourseState"],
    "resumo_por_certificacao": ["FirstName", "LastName", "UserEmail", "Teams", "CertificationName", "StartedAt", "EndedAt", "Status"],
    "resumo": ["FirstName", "LastName", "UserEmail", "UserName", "Teams", "DateUserJoinedGroup", "DateUserLeftGroup", "TotalXp", "DateOfLastXPEarned", "NumExercisesCompleted", "NumChaptersCompleted", "NumCoursesCompleted", "NumTracksCompleted", "NumPractisesCompleted", "NumProjectsCompleted", "NumAssessmentsCompleted", "CompletedCourses", "CompletedTracks", "CompletedPractises", "CompletedProjects", "CompletedAssessments"],
    "membros": ["Email", "Name", "Teams", "Role", "Learn license", "Workspace license"],
    "historico_da_equipe": ["EventTime", "EventType", "EventTargetType", "TeamData", "UserData"],
    "catalogo_de_conteudo": ["ID", "Type", "Title", "Description", "URL", "Technology", "Topic", "Skill Level", "Hours", "State", "Mobile", "ReleasedAt", "LastUpdatedAt"],
    "avaliacao_de_habilidades": ["email", "username", "nameid", "teams", "assessment name", "assessment slug", "date started", "date completed", "reported score", "reported percentile", "reported knowledge level", "attempt number"]
}

def obter_credenciais_drive():
    """Realiza o fluxo de autenticação via navegador para o Google Drive e salva o token localmente."""
    scopes = ["https://www.googleapis.com/auth/drive.readonly"]
    creds = None
    
    # Se o token temporário já existir, reutiliza ele
    if os.path.exists("token.pickle"):
        with open("token.pickle", "rb") as token:
            creds = pickle.load(token)
            
    # Se não existir ou estiver expirado, abre o navegador para o usuário logar
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists("client_secret.json"):
                raise FileNotFoundError("O arquivo client_secret.json nao foi encontrado na raiz do projeto!")
            
            flow = InstalledAppFlow.from_client_secrets_file("client_secret.json", scopes)
            creds = flow.run_local_server(port=0)
            
        # Salva o token para não precisar logar toda vez que rodar o script
        with open("token.pickle", "wb") as token:
            pickle.dump(creds, token)
            
    return creds

def obter_credenciais_gcs():
    """Retorna as credenciais nativas do sistema (ADC) para o Cloud Storage."""
    scopes = ["https://www.googleapis.com/auth/devstorage.read_write"]
    creds, _ = default(scopes=scopes)
    return creds

def baixar_arquivos_do_drive(id_pasta_drive: str, pasta_local_destino: pathlib.Path) -> list[pathlib.Path]:
    """Lista e faz o download de todos os CSVs brutos do Drive para o ambiente local."""
    log.info("Conectando ao Google Drive...")
    
    creds = obter_credenciais_drive()
    service = build("drive", "v3", credentials=creds)
    
    pasta_local_destino.mkdir(exist_ok=True)
    arquivos_baixados = []
    
    # Query definitiva usando o mimeType exato que o diagnóstico validou
    query = f"'{id_pasta_drive}' in parents and mimeType = 'text/csv' and trashed = false"
    
    # Mantemos os parâmetros que solucionaram o acesso à pasta compartilhada
    resultados = service.files().list(
        q=query, 
        fields="files(id, name)",
        supportsAllDrives=True,
        includeItemsFromAllDrives=True
    ).execute()
    
    itens = resultados.get("files", [])
    
    if not itens:
        log.warning("Nenhum CSV encontrado na pasta do Drive.")
        return arquivos_baixados

    for item in itens:
        file_id = item["id"]
        file_name = item["name"]
        caminho_local = pasta_local_destino / file_name
        
        log.info("Efetuando download: %s", file_name)
        requisicao = service.files().get_media(fileId=file_id)
        with io.FileIO(caminho_local, "wb") as fh:
            downloader = MediaIoBaseDownload(fh, requisicao)
            done = False
            while not done:
                _, done = downloader.next_chunk()
                
        arquivos_baixados.append(caminho_local)
        
    return arquivos_baixados

def enviar_csv_original_para_gcs(project: str, bucket_name: str, caminho_arquivo: pathlib.Path) -> None:
    """Faz upload do CSV original e inalterado diretamente para a camada RAW do bucket."""
    log.info("Enviando CSV original para o Storage: %s", caminho_arquivo.name)
    
    # Usa o fluxo original do terminal (ADC) que é mais seguro para a GCP
    creds = obter_credenciais_gcs()
    client = storage.Client(project=project, credentials=creds)
    bucket = client.bucket(bucket_name)
    
    rota_na_nuvem = f"datacamp/raw_csvs/{caminho_arquivo.name}"
    blob = bucket.blob(rota_na_nuvem)
    
    blob.upload_from_filename(str(caminho_arquivo))
    log.info("CSV original salvo em: gs://%s/%s", bucket_name, rota_na_nuvem)

def ler_cabecalho(caminho_do_arquivo: pathlib.Path) -> list[str]:
    # Alterado para utf-8-sig para limpar caracteres invisíveis de BOM
    with open(caminho_do_arquivo, mode='r', encoding='utf-8-sig') as f:
        leitor = csv.reader(f)
        cabecalho_original = next(leitor)
    # O .replace("\r", "").replace("\n", "") garante a remoção de quebras de linha invisíveis
    return [coluna.strip().lower().replace("\r", "").replace("\n", "") for coluna in cabecalho_original] 

def classificar_relatorio(cabecalho_arquivo: list[str]) -> str:
    # Junta tudo em uma única string limpa para buscar os termos dentro
    texto_cabecalho = " ".join(cabecalho_arquivo).lower()
    
    # Se contiver os termos únicos do tempo de aprendizado, classifica direto
    if "courses (classic)" in texto_cabecalho and "alltypes" in texto_cabecalho:
        return "tempo_no_aprendizado"
        
    # Mantém o fluxo padrão para as outras tabelas
    for nome_relatorio, colunas_esperadas in MAPEAMENTO_RELATORIOS.items():
        colunas_gabarito_limpas = {col.strip().lower() for col in colunas_esperadas}
        if colunas_gabarito_limpas.issubset(set(cabecalho_arquivo)):
            return nome_relatorio
            
    return "desconhecido"

def converter_csv_para_parquet(
    caminho_csv: pathlib.Path, tipo_relatorio: str
) -> pathlib.Path:
    log.info("Convertendo %s para Parquet...", caminho_csv.name)
    df = pd.read_csv(caminho_csv, dtype=str, encoding="utf-8-sig")

    # Padroniza os nomes das colunas
    df.columns = (
        df.columns.str.strip()
        .str.lower()
        .str.replace("%", "pct")
        .str.replace(" ", "_")
        .str.replace("(", "")
        .str.replace(")", "")
    )

    # --- INÍCIO DA TASK DE ANONIMIZAÇÃO ---
    # Identifica a coluna de e-mail presente no relatório (pode ser 'email' ou 'useremail')
    coluna_email = None
    if "email" in df.columns:
        coluna_email = "email"
    elif "useremail" in df.columns:
        coluna_email = "useremail"

    if coluna_email:
        log.info("Anonimizando coluna sensível '%s'...", coluna_email)
        # Preenche valores nulos para evitar falha no hash e aplica o SHA-256 com salt
        df["user_id"] = (
            df[coluna_email].fillna("").astype(str).apply(gerar_user_id)
        )

        # CRÍTICO: Descarta a coluna original com o e-mail
        df.drop(columns=[coluna_email], inplace=True)
    # --- FIM DA TASK DE ANONIMIZAÇÃO ---

    pasta_saida = pathlib.Path("dados_processados")
    pasta_saida.mkdir(exist_ok=True)
    caminho_parquet = pasta_saida / f"{tipo_relatorio}.parquet"

    df.to_parquet(
        caminho_parquet, engine="pyarrow", compression="snappy", index=False
    )
    df_parquet = pd.read_parquet(caminho_parquet)

    if len(df) != len(df_parquet):
        raise ValueError(
            f"Falha na conversão: CSV possui {len(df)} linhas e o Parquet possui {len(df_parquet)} linhas."
        )

    log.info("Salvo localmente em Parquet: %s", caminho_parquet)
    return caminho_parquet

def run() -> None:
    load_dotenv()
    log.info("Iniciando Job de Ingestao (Drive -> GCS CSV Raw)...")
    
    # 1. Variáveis de ambiente
    project = os.environ.get("GCP_PROJECT", "projeto-local")
    raw_bucket = os.environ.get("RAW_BUCKET", "bucket-local")  # Usando a mesma variável para manter a consistência
    id_pasta_drive = os.environ.get("GOOGLE_DRIVE_FOLDER_ID")
    
    if not id_pasta_drive:
        log.error("A variavel GOOGLE_DRIVE_FOLDER_ID nao esta configurada!")
        return

    pasta_inputs = pathlib.Path("dados_teste")
    
    # 2. Ingestão dos CSVs
    try:
        arquivos_baixados = baixar_arquivos_do_drive(id_pasta_drive, pasta_inputs)
    except Exception as e:
        log.error("Erro ao baixar arquivos do Drive: %s", str(e))
        return

    # 3. Upload Raw (CSV) e transformação local para Parquet
    for arquivo in arquivos_baixados:
        try:
            # Garante que o arquivo bruto (CSV) chegue na nuvem inalterado
            enviar_csv_original_para_gcs(project, raw_bucket, arquivo)
            
            # Executa apenas a classificação e conversão local para Parquet
            cabecalho = ler_cabecalho(arquivo)
            tipo_relatorio = classificar_relatorio(cabecalho)
            log.info("Arquivo: %s | Classificado como: %s", arquivo.name, tipo_relatorio)
            
            if tipo_relatorio != "desconhecido":
                converter_csv_para_parquet(arquivo, tipo_relatorio)
            else:
                log.warning("Arquivo %s nao convertido por ser desconhecido.", arquivo.name)
                
        except Exception as e:
            log.error("Erro ao processar o arquivo %s: %s", arquivo.name, str(e))

if __name__ == "__main__":
    run()