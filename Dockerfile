FROM python:3.12-slim

# Fuso do container: mantém os logs no horário local. As decisões de
# horário/data no código usam TIMEZONE explicitamente (ver calendar_api),
# então não dependem desta variável.
ENV TZ=America/Fortaleza

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ src/

CMD ["python", "-m", "src.agent"]
