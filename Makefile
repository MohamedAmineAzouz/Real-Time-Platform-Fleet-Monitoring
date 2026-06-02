# Makefile for IoT Platform Orchestration

# Common variables
ENV_FILE=../../$(ENV_FILE_NAME)
ENV_FILE_NAME=.env
DOCKER_COMPOSE=docker compose --env-file $(ENV_FILE)

# Components
TOOLS_DIR=tools
APPLICATION_DIR=application
SPEED_LAYER_DIR=processing/speed_layer_2
BATCH_LAYER_DIR=processing/batch_layer_2/airflow

.PHONY: all up down stop restart ps tools app speed batch logs-tools logs-app logs-speed logs-batch help

help:
	@echo "Available commands:"
	@echo "  make all           - Start all components (tools, app, speed, batch)"
	@echo "  make up            - Alias for make all"
	@echo "  make down          - Stop and remove all containers"
	@echo "  make stop          - Stop all containers without removing them"
	@echo "  make restart       - Restart all components"
	@echo "  make ps            - Show status of all containers"
	@echo "  make tools         - Start infrastructure (Kafka, Cassandra, MinIO, etc.)"
	@echo "  make app           - Start simulators, backend, and frontend"
	@echo "  make speed         - Start Spark streaming (Speed Layer)"
	@echo "  make batch         - Start Airflow cluster (Batch Layer)"
	@echo "  make logs-tools    - Show logs for tools"
	@echo "  make logs-app      - Show logs for application"
	@echo "  make logs-speed    - Show logs for speed layer"
	@echo "  make logs-batch    - Show logs for batch layer"

all: tools speed batch app

up: all

tools:
	@echo "Starting Infrastructure Tools..."
	cd $(TOOLS_DIR) && docker compose --env-file ../.env.dev up -d
	@echo "Waiting for Cassandra and Kafka to be healthy..."
	@sleep 30

speed:
	@echo "Starting Speed Layer (Spark Streaming)..."
	cd $(SPEED_LAYER_DIR) && docker compose --env-file ../../.env.dev up -d

app:
	@echo "Starting Application (Simulators, Backend, Frontend)..."
	cd $(APPLICATION_DIR) && docker compose --env-file ../.env.dev up -d
	
batch:
	@echo "Starting Batch Layer (Airflow)..."
	cd $(BATCH_LAYER_DIR) && docker compose --env-file ../../../.env.dev up -d



down:
	cd $(APPLICATION_DIR) && docker compose --env-file ../.env.dev down
	cd $(SPEED_LAYER_DIR) && docker compose --env-file ../../.env.dev down
	cd $(BATCH_LAYER_DIR) && docker compose --env-file ../../../.env.dev down
	cd $(TOOLS_DIR) && docker compose --env-file ../.env.dev down

stop:
	cd $(APPLICATION_DIR) && docker compose --env-file ../.env.dev stop
	cd $(SPEED_LAYER_DIR) && docker compose --env-file ../../.env.dev stop
	cd $(BATCH_LAYER_DIR) && docker compose --env-file ../../../.env.dev stop
	cd $(TOOLS_DIR) && docker compose --env-file ../.env.dev stop

restart: stop up

ps:
	@echo "--- Infrastructure Tools ---"
	cd $(TOOLS_DIR) && docker compose --env-file ../.env.dev ps
	@echo "\n--- Speed Layer ---"
	cd $(SPEED_LAYER_DIR) && docker compose --env-file ../../.env.dev ps
	@echo "\n--- Batch Layer ---"
	cd $(BATCH_LAYER_DIR) && docker compose --env-file ../../../.env.dev ps
	@echo "\n--- Application ---"
	cd $(APPLICATION_DIR) && docker compose --env-file ../.env.dev ps

logs-tools:
	cd $(TOOLS_DIR) && docker compose --env-file ../.env.dev logs -f

logs-app:
	cd $(APPLICATION_DIR) && docker compose --env-file ../.env.dev logs -f

logs-speed:
	cd $(SPEED_LAYER_DIR) && docker compose --env-file ../../.env.dev logs -f

logs-batch:
	cd $(BATCH_LAYER_DIR) && docker compose --env-file ../../../.env.dev logs -f

