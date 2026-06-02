# ── FleetPulse Unified Orchestration (Windows Native) ──────────────────────────
# Managing Infrastructure, Speed Layer, Batch Layer, and Applications
# ─────────────────────────────────────────────────────────────────────────────

$TOOLS_COMPOSE = "tools/docker-compose.yml"
$APP_COMPOSE = "application/docker-compose.yml"
$AIRFLOW_COMPOSE = "processing/batch_layer_2/airflow/docker-compose.yaml"
$SPEED_LAYER_COMPOSE = "processing/speed_layer_2/docker-compose.yml"
$NETWORK_NAME = "iot_network"

function Show-Help {
    Write-Host "FleetPulse Control Center (Windows)" -ForegroundColor Cyan
    Write-Host "----------------------------------"
    Write-Host "Usage: .\run.ps1 [command]"
    Write-Host ""
    Write-Host "Commands:"
    Write-Host "  setup      Initialize environment (.env and Docker network)"
    Write-Host "  up         Start all layers (Infra, Speed, Batch, App)"
    Write-Host "  infra      Start Core Infrastructure (Kafka, Cassandra, MinIO, DBGate)"
    Write-Host "  speed      Start Speed Layer (Spark Cluster & Streaming Processor)"
    Write-Host "  batch      Start Batch Layer (Airflow Cluster)"
    Write-Host "  app        Start Simulation & Fleet Applications"
    Write-Host "  down       Stop all services"
    Write-Host "  restart    Full system restart"
    Write-Host "  status     Show status of all platform components"
    Write-Host "  logs       Tail logs for all active services"
    Write-Host "  clean      Wipe all containers, networks, and data volumes"
}

function Setup-Env {
    Write-Host "[WAIT] Setting up environment..." -ForegroundColor Yellow
    if (-not (Test-Path ".env.dev")) {
        Copy-Item ".env.example" ".env.dev"
        Write-Host "[OK] .env.dev created from .env.example" -ForegroundColor Green
    }
    
    $networkCheck = docker network ls --filter name=$NETWORK_NAME -q
    if (-not $networkCheck) {
        docker network create $NETWORK_NAME
        Write-Host "[OK] Network $NETWORK_NAME created" -ForegroundColor Green
    }
}

function Start-Infra {
    Setup-Env
    Write-Host "[START] Starting Core Infrastructure..." -ForegroundColor Yellow
    docker compose --env-file ./.env.dev -f $TOOLS_COMPOSE up -d 
}

function Start-Speed {
    Setup-Env
    Write-Host "[START] Starting Speed Layer (Spark Cluster)..." -ForegroundColor Yellow
    docker compose --env-file ./.env.dev -f $SPEED_LAYER_COMPOSE up -d
}

function Start-Batch {
    Setup-Env
    Write-Host "[START] Starting Batch Layer (Airflow)..." -ForegroundColor Yellow
    docker compose --env-file ./.env.dev -f $AIRFLOW_COMPOSE up -d
}

function Start-App {
    Setup-Env
    Write-Host "[START] Starting Fleet Applications..." -ForegroundColor Yellow
    docker compose --env-file ./.env.dev -f $APP_COMPOSE up -d
}

function Start-All {
    Start-Infra
    Start-Speed
    Start-App
    Start-Batch
    Write-Host ""
    Write-Host "[DONE] System fully operational!" -ForegroundColor Cyan
}

function Stop-All {
    Write-Host "[STOP] Shutting down FleetPulse..." -ForegroundColor Red
    docker compose -f $APP_COMPOSE down
    docker compose -f $AIRFLOW_COMPOSE down
    docker compose -f $TOOLS_COMPOSE down
    Write-Host "[OK] All services stopped." -ForegroundColor Green
}

function Show-Status {
    Write-Host "--- Infrastructure ---" -ForegroundColor Cyan
    docker compose -f $TOOLS_COMPOSE ps
    Write-Host "--- Speed Layer (Spark) ---" -ForegroundColor Cyan
    docker compose -f $TOOLS_COMPOSE ps
    Write-Host "--- Batch Layer (Airflow) ---" -ForegroundColor Cyan
    docker compose -f $AIRFLOW_COMPOSE ps
    Write-Host "--- Simulation & Apps ---" -ForegroundColor Cyan
    docker compose -f $APP_COMPOSE ps
}

function Tail-Logs {
    Write-Host "[LOGS] Tailing all logs (Ctrl+C to stop)..." -ForegroundColor Yellow
    docker compose -f $TOOLS_COMPOSE -f $AIRFLOW_COMPOSE -f $APP_COMPOSE logs -f --tail=100
}

function Clean-All {
    Write-Host "[DANGER] Wiping entire platform state..." -ForegroundColor Red
    docker compose -f $APP_COMPOSE down -v
    docker compose -f $AIRFLOW_COMPOSE down -v
    docker compose -f $TOOLS_COMPOSE down -v
    docker network rm $NETWORK_NAME
    Write-Host "[DONE] Environment is now clean." -ForegroundColor Green
}

# ── Command Router ──────────────────────────────────────────────────────────
if ($args.Count -eq 0) {
    Show-Help
} else {
    $command = $args[0]
    switch ($command) {
        "up"      { Start-All }
        "infra"   { Start-Infra }
        "speed"   { Start-Speed }
        "batch"   { Start-Batch }
        "app"     { Start-App }
        "down"    { Stop-All }
        "restart" { Stop-All; Start-All }
        "status"  { Show-Status }
        "logs"    { Tail-Logs }
        "clean"   { Clean-All }
        "setup"   { Setup-Env }
        default   { Show-Help }
    }
}
