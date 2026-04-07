import json
import logging
import os
from datetime import datetime, timedelta

import httpx

from src.calendar_api import get_timezone, RECURRENCE_MAP

logger = logging.getLogger(__name__)

GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"

VALID_INTENTS = [
    "criar_evento",
    "editar_evento",
    "excluir_evento",
    "listar_eventos_hoje",
    "listar_eventos_amanha",
    "listar_eventos_semana",
    "horarios_livres",
    "criar_tarefa",
    "listar_tarefas",
    "concluir_tarefa",
    "excluir_tarefa",
    "desconhecido",
]


def _get_groq_key() -> str | None:
    return os.getenv("GROQ_API_KEY")


async def _call_groq(prompt: str) -> str | None:
    api_key = _get_groq_key()
    if not api_key:
        logger.warning("GROQ_API_KEY não configurada")
        return None

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
                    "max_tokens": 300,
                },
            )

            if response.status_code != 200:
                logger.error(f"Groq API erro: {response.status_code} {response.text}")
                return None

            data = response.json()
            content = data["choices"][0]["message"]["content"].strip()

            if content.startswith("```"):
                content = content.split("\n", 1)[1]
                content = content.rsplit("```", 1)[0]

            return content

    except Exception as e:
        logger.error(f"Erro ao chamar Groq API: {e}")
        return None


def _build_intent_prompt(user_message: str, now: datetime) -> str:
    intents_list = ", ".join(VALID_INTENTS)
    recurrence_options = ", ".join(RECURRENCE_MAP.keys())

    return f"""Você é um assistente de agenda que interpreta mensagens em linguagem natural.

Data/hora atual: {now.strftime("%d/%m/%Y %H:%M")} ({now.strftime("%A")})

Analise a mensagem do usuário e retorne APENAS um JSON válido com:
- "intent": a intenção do usuário. Opções: {intents_list}
- "title": título do evento/tarefa (string ou null)
- "date": data no formato dd/mm/aaaa (string ou null)
- "time": horário no formato hh:mm (string ou null)
- "recurrence": recorrência se mencionada ({recurrence_options}) ou null
- "search_term": termo para buscar evento/tarefa quando for editar/excluir/concluir (string ou null)

Regras:
- "hoje" = {now.strftime("%d/%m/%Y")}
- "amanhã" = {(now + timedelta(days=1)).strftime("%d/%m/%Y")}
- Se disser "segunda", "terça", etc., calcule a próxima data correspondente
- Se não mencionar horário em criação de evento, use "09:00"
- Se não mencionar recorrência, use null
- Para edição/exclusão, extraia o search_term que identifica o evento (ex: "reunião", "dentista")
- Para "o que tenho hoje?", "meus eventos", etc., use listar_eventos_hoje
- Para "semana", "próximos dias", use listar_eventos_semana
- Para "estou livre?", "horários vagos", use horarios_livres
- Para "tarefa", "to-do", "preciso fazer", use criar_tarefa
- Se não conseguir determinar a intenção, use "desconhecido"
- Responda APENAS com o JSON, sem texto adicional

Mensagem: "{user_message}"
"""


def _build_event_prompt(user_message: str, now: datetime) -> str:
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


async def parse_intent(user_message: str) -> dict | None:
    api_key = _get_groq_key()
    if not api_key:
        return None

    tz = get_timezone()
    now = datetime.now(tz)

    prompt = _build_intent_prompt(user_message, now)
    content = await _call_groq(prompt)

    if not content:
        return None

    try:
        parsed = json.loads(content)
        if parsed.get("intent") not in VALID_INTENTS:
            parsed["intent"] = "desconhecido"
        return parsed
    except (json.JSONDecodeError, KeyError):
        return None


async def parse_event_from_text(user_message: str) -> dict | None:
    api_key = _get_groq_key()
    if not api_key:
        logger.warning("GROQ_API_KEY não configurada")
        return None

    tz = get_timezone()
    now = datetime.now(tz)

    prompt = _build_event_prompt(user_message, now)
    content = await _call_groq(prompt)

    if not content:
        return None

    try:
        parsed = json.loads(content)
        if not parsed.get("title") or not parsed.get("date") or not parsed.get("time"):
            return None
        return parsed
    except (json.JSONDecodeError, KeyError):
        return None
