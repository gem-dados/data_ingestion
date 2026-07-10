"""Job de identificacao de relatorios DataCamp.

Ler dinamicamente o cabeçalho dos arquivos e classificar os 10 tipos de relatórios.

"""

from __future__ import annotations

import json
import csv
import logging
import os
import pathlib
from datetime import datetime, timezone

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("ingestion")

""" Esse dicionário serve como o "gabarito" para identificar os relatórios."""
MAPEAMENTO_RELATORIOS = {
    "tempo_no_aprendizado": ["FirstName", "LastName", "Email", "AllTypes", "Courses(Classic)", "Courses(AI Native)", "Courses", "Assessments", "Projects", "Practices"],
    "resumo_por_projeto": ["FirstName", "LastName", "UserEmail", "Teams", "ProjectId", "ProjectName", "Technology", "StartedAt", "CompletedAt"],
    "resumo_por_programa": ["FirstName", "LastName", "UserEmail", "Teams", "TrackId", "TrackVersionId", "TrackTitle", "Technology", "StartedAt", "CompletedAt", "% XP Earned", "Hours Spent", "NumCourses", "NumCoursesCompleted", "NumChapters", "NumChaptersCompleted", "NumProjects", "NumProjectsCompleted", "NumAssessments", "NumAssessmentsCompleted"],
    "resumo_por_curso": ["FirstName", "LastName", "UserEmail", "UserName", "Teams", "JoinedGroup", "LeftGroup", "CourseId", "CourseName", "Technology", "StartedCourse", "FinishedCourse", "SkippedCourse", "LastVisitedCourse", "CompletedCourseExercises", "CourseCompletionRate", "CourseStatus", "TotalCourseXPEarned", "TotalCourseXPAvailable", "XPScore", "CourseState"],
    "resumo_por_certificacao": ["FirstName", "LastName", "UserEmail", "Teams", "CertificationName", "StartedAt", "EndedAt", "Status"],
    "resumo": ["FirstName", "LastName", "UserEmail", "UserName", "Teams", "DateUserJoinedGroup", "DateUserLeftGroup", "TotalXp", "DateOfLastXPEarned", "NumExercisesCompleted", "NumChaptersCompleted", "NumCoursesCompleted", "NumTracksCompleted", "NumPractisesCompleted", "NumProjectsCompleted", "NumAssessmentsCompleted", "CompletedCourses", "CompletedTracks", "CompletedPractises", "CompletedProjects", "CompletedAssessments"],
    "membros": ["Email", "Name", "Teams", "Role", "Learn license", "Workspace license"],
    "historico_da_equipe": ["EventTime", "EventType", "EventTargetType", "TeamData", "UserData"],
    "catalogo_de_conteudo": ["ID", "Type", "Title", "Description", "URL", "Technology", "Topic", "Skill Level", "Hours", "State", "Mobile", "ReleasedAt", "LastUpdatedAt"],
    "avaliacao_de_habilidades": ["Email", "Username", "NameID", "Teams", "Assessment Name", "Assessment Slug", "Date Started", "Date Completed", "Reported Score", "Reported Percentile", "Reported Knowledge", "Attempt Number"]
}

def ler_cabecalho(caminho_do_arquivo: pathlib.Path) -> list[str]:
    """Abre o arquivo e retorna o cabeçalho limpo (sem espaços e em minúsculo)."""
    with open(caminho_do_arquivo, mode='r', encoding='utf-8') as f:
        leitor = csv.reader(f)
        cabecalho_original = next(leitor)
    
    # LIMPEZA: Remove espaços em branco das pontas e joga tudo para minúsculo
    cabecalho_limpo = [coluna.strip().lower() for coluna in cabecalho_original]
    return cabecalho_limpo

def classificar_relatorio(cabecalho_arquivo: list[str]) -> str:
    """Compara o cabeçalho com o gabarito (que também deve estar em minúsculo)."""
    colunas_arquivo = set(cabecalho_arquivo)
    
    for nome_relatorio, colunas_esperadas in MAPEAMENTO_RELATORIOS.items():
        # Garante que o gabarito também seja comparado em minúsculo e sem espaços
        colunas_gabarito_limpas = {col.strip().lower() for col in colunas_esperadas}
        
        if colunas_gabarito_limpas.issubset(colunas_arquivo):
            return nome_relatorio
            
    return "desconhecido"

import pandas as pd

def converter_csv_para_parquet(caminho_csv: pathlib.Path, tipo_relatorio: str) -> pathlib.Path:
    """Lê o CSV via Pandas, limpa os nomes das colunas e salva em formato Parquet."""
    log.info("Convertendo %s para formato Parquet...", caminho_csv.name)
    
    # 1. Ler o CSV forçando todas as colunas como string para evitar erros de inferência
    df = pd.read_csv(caminho_csv, dtype=str)
    
    # 2. LIMPEZA DE CABEÇALHO: Remove espaços, deixa minúsculo e substitui caracteres especiais
    # Ex: "% XP Earned" vira "pct_xp_earned" | "User Name" vira "user_name"
    df.columns = (
        df.columns.str.strip()
        .str.lower()
        .str.replace("%", "pct")
        .str.replace(" ", "_")
        .str.replace("(", "")
        .str.replace(")", "")
    )
    
    # 3. Definir onde o arquivo Parquet será salvo
    # Vamos criar uma pasta chamada 'dados_processados' para não misturar com os CSVs
    pasta_saida = pathlib.Path("dados_processados")
    pasta_saida.mkdir(exist_ok=True) # Cria a pasta se ela não existir
    
    # O nome do arquivo final será o tipo limpo do relatório + extensão .parquet
    caminho_parquet = pasta_saida / f"{tipo_relatorio}.parquet"
    
    # 4. Salvar em Parquet usando a engine pyarrow e compressão snappy (padrão de mercado)
    df.to_parquet(caminho_parquet, engine="pyarrow", compression="snappy", index=False)
    
    log.info("Arquivo salvo com sucesso em: %s", caminho_parquet)
    return caminho_parquet

def run() -> None:
    log.info("Iniciando o Job de identificacao de relatorios DataCamp")
    
    # 1. Leitura de variáveis de ambiente
    project = os.environ.get("GCP_PROJECT", "projeto-local")
    env = os.environ.get("ENVIRONMENT", "stg")
    
    # 2. Lógica para escanear uma pasta local com os CSVs de teste
    pasta_inputs = pathlib.Path("dados_teste")
    
    if not pasta_inputs.exists():
        log.warning("A pasta '%s' nao existe. Crie-a para colocar os CSVs de teste.", pasta_inputs)
        return

    # Loop dinâmico para ler todos os CSVs da pasta
    for arquivo in pasta_inputs.glob("*.csv"):
        try:
            cabecalho = ler_cabecalho(arquivo)
            tipo_relatorio = classificar_relatorio(cabecalho)
            log.info("Arquivo: %s | Classificado como: %s", arquivo.name, tipo_relatorio)
            
            # === NOVA LÓGICA DA TASK 1.5 CONECTADA AQUI ===
            if tipo_relatorio != "desconhecido":
                caminho_final = converter_csv_para_parquet(arquivo, tipo_relatorio)
            else:
                log.warning("Arquivo %s nao foi convertido por ser desconhecido.", arquivo.name)
            # ============================================
            
        except Exception as e:
            log.error("Erro ao processar o arquivo %s: %s", arquivo.name, str(e))

if __name__ == "__main__":
    run()
