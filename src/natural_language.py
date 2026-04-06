import json
import logging
import os
from datetime import datetime, timedelta

import httpx

from src.calendar_api import get_timezone, RECURRENCE_MAP

logger = logging.getLogger(__name__)

GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"


def _get_groq_key() -> str | None:
    return os.getenv("GROQ_API_KEY")


def _build_prompt(user_message: str, now: datetime) -> str:
    recurrence_options = ", ".join(RECURRENCE_MAP.keys())
    return f"""Você é um assistente que extrai informações de eventos de agenda a partir de mensagens em linguagem natural.

Data/hora atual: {now.strftime("%d/%m/%Y %H:%M")} ({now.strftime("%A")})

Extraia as seguintes informações da mensagem do usuário e retorne APENAS um JSON válido:
- "title": título do evento (string)
- "date": data no formato dd/mm/aaaa (string)
- "time": horário no formato hh:mm (string)
- "recurrence": recorrência se mencionada, opções: {recurrence_options} ou null

Regras:
- "hoje" = {now.strftime("%d/%m/%Y")}
- "amanhã" = {(now + timedelta(days=1)).strftime("%d/%m/%Y")}
- Se disser "segunda", "terça", etc., calcule a próxima data correspondente
- Se não mencionar horário, use "09:00" como padrão
- Se não mencionar recorrência, use null
- Responda APENAS com o JSON, sem texto adicional

Mensagem: "{user_message}"
"""


async def parse_event_from_text(user_message: str) -> dict | None:
    api_key = _get_groq_key()
    if not api_key:
        logger.warning("GROQ_API_KEY não configurada")
        return None

    tz = get_timezone()
    now = datetime.now(tz)

    prompt = _build_prompt(user_message, now)

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.post(
                GROQ_API_URL,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "llama-3.3-70b-versatile",
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.1,
                    "max_tokens": 200,
                },
            )

            if response.status_code != 200:
                logger.error(f"Groq API erro: {response.status_code} {response.text}")
                return None

            data = response.json()
            content = data["choices"][0]["message"]["content"].strip()

            # Remove possíveis marcadores de código
            if content.startswith("```"):
                content = content.split("\n", 1)[1]
                content = content.rsplit("```", 1)[0]

            parsed = json.loads(content)

            if not parsed.get("title") or not parsed.get("date") or not parsed.get("time"):
                return None

            return parsed

    except Exception as e:
        logger.error(f"Erro ao processar linguagem natural: {e}")
        return None
