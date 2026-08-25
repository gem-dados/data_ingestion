"""Job de identificacao e ingestao de relatorios DataCamp.

Faz a ingestão dos CSVs disponibilizados no Google Drive via Google API (com conta de serviço/ADC).
Lê dinamicamente o cabeçalho dos arquivos, classifica os tipos de relatórios,
anonimiza dados sensíveis e grava os arquivos Parquet diretamente no Google Cloud Storage (sem estado local).
"""

from __future__ import annotations

import csv
import io
import logging
import os
import pathlib

from dotenv import load_dotenv
import pandas as pd

# Google APIs
from google.auth import default
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from google.cloud import storage  # type: ignore

from src.utils.crypto import gerar_user_id

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

SCOPES_DRIVE = ["https://www.googleapis.com/auth/drive.readonly"]
SCOPES_GCS = ["https://www.googleapis.com/auth/devstorage.read_write"]


def obter_credenciais_drive():
    """Retorna as credenciais para o Google Drive via Application Default Credentials (ADC)."""
    creds, _ = default(scopes=SCOPES_DRIVE)
    return creds


def obter_credenciais_gcs():
    """Retorna as credenciais nativas do sistema (ADC) para o Cloud Storage."""
    creds, _ = default(scopes=SCOPES_GCS)
    return creds


def baixar_arquivos_do_drive_em_memoria(id_pasta_drive: str) -> list[tuple[str, io.BytesIO]]:
    """Lista e faz o download de todos os CSVs do Drive diretamente em memória (sem salvar no disco)."""
    log.info("Conectando ao Google Drive via Service Account / ADC...")

    creds = obter_credenciais_drive()
    service = build("drive", "v3", credentials=creds)

    query = f"'{id_pasta_drive}' in parents and mimeType = 'text/csv' and trashed = false"

    resultados = service.files().list(
        q=query,
        fields="files(id, name)",
        supportsAllDrives=True,
        includeItemsFromAllDrives=True
    ).execute()

    itens = resultados.get("files", [])
    if not itens:
        log.warning("Nenhum CSV encontrado na pasta do Drive: %s", id_pasta_drive)
        return []

    arquivos_em_memoria = []
    for item in itens:
        file_id = item["id"]
        file_name = item["name"]
        log.info("Baixando do Drive para memória: %s", file_name)

        buffer = io.BytesIO()
        requisicao = service.files().get_media(fileId=file_id)
        downloader = MediaIoBaseDownload(buffer, requisicao)
        done = False
        while not done:
            _, done = downloader.next_chunk()

        buffer.seek(0)
        arquivos_em_memoria.append((file_name, buffer))

    return arquivos_em_memoria


def enviar_csv_original_para_gcs(bucket: storage.Bucket, file_name: str, buffer_csv: io.BytesIO) -> None:
    """Faz upload do CSV original inalterado diretamente da memória para o GCS."""
    log.info("Enviando CSV original para o Storage: %s", file_name)
    buffer_csv.seek(0)

    rota_na_nuvem = f"datacamp/raw_csvs/{file_name}"
    blob = bucket.blob(rota_na_nuvem)
    blob.upload_from_file(buffer_csv, content_type="text/csv")
    buffer_csv.seek(0)
    log.info("CSV original salvo em: gs://%s/%s", bucket.name, rota_na_nuvem)


def ler_cabecalho(conteudo_csv: io.BytesIO | pathlib.Path | str) -> list[str]:
    """Lê a primeira linha do CSV e retorna as colunas tratadas."""
    if isinstance(conteudo_csv, io.BytesIO):
        conteudo_csv.seek(0)
        texto = conteudo_csv.getvalue().decode("utf-8-sig", errors="ignore")
        leitor = csv.reader(io.StringIO(texto))
        cabecalho_original = next(leitor)
        conteudo_csv.seek(0)
    else:
        with open(conteudo_csv, mode="r", encoding="utf-8-sig") as f:
            leitor = csv.reader(f)
            cabecalho_original = next(leitor)

    return [coluna.strip().lower().replace("\r", "").replace("\n", "") for coluna in cabecalho_original]


def classificar_relatorio(cabecalho_arquivo: list[str]) -> str:
    """Classifica o tipo de relatório a partir do cabeçalho."""
    texto_cabecalho = " ".join(cabecalho_arquivo).lower()

    if "courses (classic)" in texto_cabecalho and "alltypes" in texto_cabecalho:
        return "tempo_no_aprendizado"

    for nome_relatorio, colunas_esperadas in MAPEAMENTO_RELATORIOS.items():
        colunas_gabarito_limpas = {col.strip().lower() for col in colunas_esperadas}
        if colunas_gabarito_limpas.issubset(set(cabecalho_arquivo)):
            return nome_relatorio

    return "desconhecido"


def processar_csv(conteudo_csv: io.BytesIO | pathlib.Path | str) -> pd.DataFrame:
    """Processa o CSV: padroniza nomes de colunas e anonimiza e-mails sensíveis."""
    if isinstance(conteudo_csv, io.BytesIO):
        conteudo_csv.seek(0)
        df = pd.read_csv(conteudo_csv, dtype=str, encoding="utf-8-sig")
        conteudo_csv.seek(0)
    else:
        df = pd.read_csv(conteudo_csv, dtype=str, encoding="utf-8-sig")

    df.columns = (
        df.columns.str.strip()
        .str.lower()
        .str.replace("%", "pct")
        .str.replace(" ", "_")
        .str.replace("(", "")
        .str.replace(")", "")
    )

    # Anonimização de colunas de e-mail (LGPD)
    coluna_email = None
    if "email" in df.columns:
        coluna_email = "email"
    elif "useremail" in df.columns:
        coluna_email = "useremail"

    if coluna_email:
        log.info("Anonimizando coluna sensível '%s'...", coluna_email)
        df["user_id"] = (
            df[coluna_email].fillna("").astype(str).apply(gerar_user_id)
        )
        df.drop(columns=[coluna_email], inplace=True)

    return df


def converter_csv_para_parquet(
    caminho_csv: pathlib.Path | str | io.BytesIO, tipo_relatorio: str = "relatorio"
) -> pathlib.Path | io.BytesIO:
    """Converte CSV para Parquet em memória (ou arquivo se passado Path)."""
    df = processar_csv(caminho_csv)
    buffer = io.BytesIO()
    df.to_parquet(buffer, engine="pyarrow", compression="snappy", index=False)
    buffer.seek(0)

    if isinstance(caminho_csv, (str, pathlib.Path)):
        caminho_parquet = pathlib.Path(caminho_csv).with_suffix(".parquet")
        with open(caminho_parquet, "wb") as f:
            f.write(buffer.getvalue())
        return caminho_parquet

    return buffer


def enviar_parquet_para_gcs(bucket: storage.Bucket, tipo_relatorio: str, df: pd.DataFrame) -> None:
    """Serializa DataFrame em Parquet em memória e faz o upload direto para o GCS."""
    log.info("Serializando e enviando Parquet para GCS: %s...", tipo_relatorio)

    buffer = io.BytesIO()
    df.to_parquet(buffer, engine="pyarrow", compression="snappy", index=False)
    buffer.seek(0)

    rota_na_nuvem = f"datacamp/raw/{tipo_relatorio}/{tipo_relatorio}.parquet"
    blob = bucket.blob(rota_na_nuvem)
    blob.upload_from_file(buffer, content_type="application/octet-stream")

    log.info("Parquet salvo no GCS em: gs://%s/%s (%d linhas)", bucket.name, rota_na_nuvem, len(df))


def run() -> None:
    """Executa a ingestão sem estado local: Drive -> Memória -> GCS."""
    load_dotenv()
    log.info("Iniciando Job de Ingestao sem estado local (Drive -> Memória -> GCS)...")

    project = os.environ.get("GCP_PROJECT", "gem-dados-lake-stg")
    raw_bucket = os.environ.get("RAW_BUCKET", "gem-dados-lake-stg-raw")
    id_pasta_drive = os.environ.get("GOOGLE_DRIVE_FOLDER_ID")

    if not id_pasta_drive:
        msg = "A variavel GOOGLE_DRIVE_FOLDER_ID nao esta configurada no ambiente!"
        log.error(msg)
        raise ValueError(msg)

    # 1. Download de todos os CSVs em memória
    try:
        arquivos_em_memoria = baixar_arquivos_do_drive_em_memoria(id_pasta_drive)
    except Exception as e:
        log.error("Erro ao baixar arquivos do Drive: %s", str(e))
        raise e

    if not arquivos_em_memoria:
        log.warning("Nenhum arquivo CSV encontrado na pasta do Drive.")
        return

    # 2. Cliente GCS
    creds_gcs = obter_credenciais_gcs()
    client = storage.Client(project=project, credentials=creds_gcs)
    bucket = client.bucket(raw_bucket)

    # 3. Processamento e upload em memória
    for file_name, buffer_csv in arquivos_em_memoria:
        try:
            # Envia CSV bruto para a camada raw_csvs do GCS
            enviar_csv_original_para_gcs(bucket, file_name, buffer_csv)

            # Classifica o relatório
            cabecalho = ler_cabecalho(buffer_csv)
            tipo_relatorio = classificar_relatorio(cabecalho)
            log.info("Arquivo: %s | Classificado como: %s", file_name, tipo_relatorio)

            if tipo_relatorio != "desconhecido":
                df = processar_csv(buffer_csv)
                enviar_parquet_para_gcs(bucket, tipo_relatorio, df)
            else:
                log.warning("Arquivo %s nao convertido por ser desconhecido.", file_name)

        except Exception as e:
            log.error("Erro ao processar o arquivo %s: %s", file_name, str(e))
            raise e


if __name__ == "__main__":
    run()