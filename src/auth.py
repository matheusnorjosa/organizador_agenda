"""
Script para autenticar a conta Google de um usuário.
Uso: python -m src.auth <nome_do_usuario>
"""

import sys

from src.calendar_api import get_calendar_service


def main():
    if len(sys.argv) < 2:
        print("Uso: python -m src.auth <nome_do_usuario>")
        print("Exemplo: python -m src.auth matheus")
        sys.exit(1)

    user_id = sys.argv[1]
    print(f"Autenticando usuário: {user_id}")
    print("Uma janela do navegador vai abrir. Faça login na conta Google e autorize o acesso.")

    get_calendar_service(user_id)

    print(f"Autenticação concluída! Token salvo em tokens/{user_id}.json")


if __name__ == "__main__":
    main()
