# data_ingestion — Jobs de ingestão (Python → Cloud Run)

Scripts Python que ingerem dados para o data lake `gem-dados`. Rodam no
**Cloud Run** (a infra é provisionada pelo repo [`cloud_iac`](https://github.com/gem-dados/cloud_iac)).

> Repo **público**, mantido por **estudantes**. Sem segredo no código:
> tudo vem de env vars / Secret Manager. Veja os guardrails abaixo.

---

## Como funciona

```
push na branch  ──►  Cloud Build  ──►  build imagem  ──►  Artifact Registry
   (stg|main)                                                    │
                                                                 ▼
                                                      deploy no Cloud Run
                                          (gem-dados-lake-stg | -prd)
```

| Branch | Ambiente | Projeto |
|---|---|---|
| `stg` | staging | `gem-dados-lake-stg` |
| `main` | produção | `gem-dados-lake-prd` |

A imagem é versionada por `SHORT_SHA`. O serviço Cloud Run, a SA dedicada, o
Artifact Registry e as permissões **já existem** (criados pelo `cloud_iac`).

---

## Estrutura

```
data_ingestion/
├── src/
│   ├── main.py              # entrypoint HTTP (Cloud Run): /healthz, /run/<job>
│   └── jobs/
│       └── example_job.py   # molde de job (copie para criar o seu)
├── Dockerfile               # imagem slim, usuário não-root
├── requirements.txt
├── cloudbuild.yaml          # build → push → deploy
├── .pre-commit-config.yaml  # gitleaks + bandit + ruff
└── .gitignore
```

---

## Rodar localmente

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

export GCP_PROJECT=gem-dados-lake-stg
export ENVIRONMENT=stg
export RAW_BUCKET=gem-dados-lake-stg-raw
gcloud auth application-default login    # credencial via ADC, sem chave JSON

python src/main.py          # sobe em http://localhost:8080
# curl -X POST localhost:8080/run/example
```

---

## Criar um job novo

1. Copie `src/jobs/example_job.py` → `src/jobs/meu_job.py` e implemente `run()`.
2. Registre em `src/main.py` no dict `JOBS`.
3. Config sensível? Crie no **Secret Manager** (via `cloud_iac`) e injete como
   `secret_env` no serviço Cloud Run — **nunca** hardcode.
4. PR → merge em `stg` (deploy stg) → valide → PR para `main` (deploy prd).

---

## Segurança (guardrails)

- `pre-commit`: **gitleaks** (anti-segredo), **bandit** (vulns Python),
  **detect-private-key**, **ruff**. Instale com:
  ```bash
  pip install pre-commit && pre-commit install
  ```
- `gitleaks` também roda na esteira antes do build.
- Cloud Run com `--no-allow-unauthenticated` (serviço fechado por padrão).
- Imagem roda como usuário não-root.
- **Sem** chave JSON de Service Account — use `gcloud auth ... login` (ADC).
