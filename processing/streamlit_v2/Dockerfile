FROM python:3.9-slim

WORKDIR /app

RUN apt-get update && \
    apt-get install ca-certificates curl gnupg -y && \
    curl -sSL https://pkgs.netbird.io/debian/public.key |  gpg --dearmor --output /usr/share/keyrings/netbird-archive-keyring.gpg && \
    echo 'deb [signed-by=/usr/share/keyrings/netbird-archive-keyring.gpg] https://pkgs.netbird.io/debian stable main' |  tee /etc/apt/sources.list.d/netbird.list 

RUN mkdir /etc/init.d/

RUN apt-get update && \
    apt-get install netbird

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8501

CMD ["streamlit", "run", "Home.py", "--server.port=8501", "--server.address=0.0.0.0"]
