from pathlib import Path
import sys


# Adiciona a pasta src ao caminho do Python
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