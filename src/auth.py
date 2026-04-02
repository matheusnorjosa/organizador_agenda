"""
Script para autenticar a conta Google de um usuário localmente.
Uso: python -m src.auth <nome_do_usuario>

Para autenticação remota, use o comando /auth no Telegram.
"""

import sys

from google_auth_oauthlib.flow import InstalledAppFlow

from src.calendar_api import SCOPES, CREDENTIALS_PATH, get_token_path


def main():
    if len(sys.argv) < 2:
        print("Uso: python -m src.auth <nome_do_usuario>")
        print("Exemplo: python -m src.auth matheus")
        sys.exit(1)

    user_id = sys.argv[1]
    print(f"Autenticando usuário: {user_id}")
    print("Uma janela do navegador vai abrir. Faça login na conta Google e autorize o acesso.")

    flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_PATH, SCOPES)
    creds = flow.run_local_server(port=0)

    token_path = get_token_path(user_id)
    with open(token_path, "w") as token_file:
        token_file.write(creds.to_json())

    print(f"Autenticação concluída! Token salvo em {token_path}")


if __name__ == "__main__":
    main()
