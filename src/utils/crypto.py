import hashlib
import os

from dotenv import load_dotenv

# Carrega as variáveis do arquivo .env
load_dotenv()


def gerar_user_id(valor_pii: str) -> str:
    """
    Gera um identificador único (user_id) utilizando SHA-256
    e um salt armazenado em variável de ambiente.
    """

    salt = os.getenv("SALT")

    if not salt:
        raise ValueError("A variável de ambiente SALT não foi definida.")

    dado = f"{valor_pii}{salt}"

    return hashlib.sha256(dado.encode("utf-8")).hexdigest()