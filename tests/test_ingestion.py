from pathlib import Path
import sys


# Adiciona a raiz e a pasta src ao caminho do Python
sys.path.append(str(Path(__file__).resolve().parents[1]))
sys.path.append(str(Path(__file__).resolve().parents[1] / "src"))

from jobs.identify_datacamp_csvs import converter_csv_para_parquet

import pandas as pd


def test_quantidade_linhas_csv_igual_parquet(tmp_path):
    # Cria um CSV temporário para simular uma entrada da ingestão
    arquivo_csv = tmp_path / "teste.csv"

    dados = pd.DataFrame(
        {
            "nome": ["Ana", "João", "Maria"],
            "curso": ["SQL", "Python", "Power BI"]
        }
    )

    dados.to_csv(arquivo_csv, index=False)

    # Executa a conversão CSV -> Parquet
    arquivo_parquet = converter_csv_para_parquet(
        arquivo_csv,
        "teste_ingestao"
    )

    # Lê os arquivos gerados
    csv_lido = pd.read_csv(arquivo_csv)
    parquet_lido = pd.read_parquet(arquivo_parquet)

    # Validação: nenhuma linha pode ser perdida
    assert len(csv_lido) == len(parquet_lido)


def test_anonimizacao_userdata_gera_user_id(tmp_path, monkeypatch):
    monkeypatch.setenv("SALT", "salt_teste_auditoria_123")
    from src.utils.crypto import gerar_user_id

    arquivo_csv = tmp_path / "historico_equipe.csv"
    dados = pd.DataFrame(
        {
            "EventTime": ["2026-03-01T10:00:00Z"],
            "EventType": ["UserJoinedTeam"],
            "EventTargetType": ["User"],
            "TeamData": ["Turma Engenharia de Dados"],
            "UserData": ["aluno.teste@empresa.com"],
        }
    )
    dados.to_csv(arquivo_csv, index=False)

    arquivo_parquet = converter_csv_para_parquet(
        arquivo_csv,
        "historico_da_equipe"
    )

    df_result = pd.read_parquet(arquivo_parquet)

    # Validacoes: userdata deve ter sido removido e user_id criado e hash consistente
    assert "userdata" not in df_result.columns
    assert "user_id" in df_result.columns
    expected_user_id = gerar_user_id("aluno.teste@empresa.com")
    assert df_result["user_id"].iloc[0] == expected_user_id
