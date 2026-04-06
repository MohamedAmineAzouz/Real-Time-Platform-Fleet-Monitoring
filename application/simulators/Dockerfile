FROM python:3.11-slim

WORKDIR /truck_simulator

COPY requirements.txt .
RUN pip install --no-cache-dir --default-timeout=300 -r requirements.txt

COPY truck_simulator/ ./truck_simulator/

CMD ["python", "truck_simulator/main.py"]