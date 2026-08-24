"""Smoke test de import: o container consegue subir?

Por que este teste existe: o Cloud Run inicia a aplicacao com
`gunicorn src.main:app`. Se qualquer modulo importado por `src.main` quebrar no
import, o container nao sobe — e isso nao aparece no build, so na hora do
deploy (ou pior, so quando alguem tenta usar).

Ja aconteceu: os modulos importam uns aos outros como `src.jobs...`, mas o
Dockerfile achatava o conteudo de `src/` em `/app`, entao `src` nao existia
dentro da imagem. Localmente passava, porque o `make` roda da raiz do repo.

Estes testes sao de import apenas: nao chamam GCP, nao precisam de credencial
e rodam em milissegundos.
"""

import importlib

import pytest

# Modulos que o entrypoint importa (direta ou indiretamente).
MODULOS = [
    "src.main",
    "src.jobs.identify_datacamp_csvs",
    "src.jobs.upload_parquet_to_gcs",
    "src.jobs.load_gcs_parquet_to_bigquery",
    "src.jobs.rotina_sem_duplicatas_job",
    "src.utils.cofre",
    "src.utils.crypto",
]


@pytest.mark.parametrize("modulo", MODULOS)
def test_modulo_importa(modulo):
    """Cada modulo do pacote precisa importar sem erro."""
    importlib.import_module(modulo)


def test_entrypoint_expoe_app():
    """O gunicorn procura por `app` em src.main — precisa existir."""
    main = importlib.import_module("src.main")
    assert hasattr(main, "app"), "src.main nao expoe 'app' (gunicorn src.main:app)"


def test_jobs_registrados_sao_chamaveis():
    """Todo job no registro do Flask precisa ser uma funcao de verdade."""
    main = importlib.import_module("src.main")
    assert main.JOBS, "nenhum job registrado em src.main.JOBS"
    for nome, funcao in main.JOBS.items():
        assert callable(funcao), f"job '{nome}' registrado mas nao e chamavel"
