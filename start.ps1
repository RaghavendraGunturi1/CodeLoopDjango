# start_dev.ps1

# --- 1. Check for and start Redis container ---
$containerName = "my-redis"
$container = docker ps -a --filter "name=$containerName" --format "{{.Names}}"

if (-not $container) {
    echo "Redis container not found. Starting a new one..."
    docker run --name $containerName -p 6380:6379 -d redis
} else {
    $containerStatus = docker ps --filter "name=$containerName" --format "{{.Status}}"
    if ($containerStatus -notlike "Up*") {
        echo "Redis container is stopped. Starting it..."
        docker start $containerName
    } else {
        echo "Redis container is already running."
    }
}

# --- 2. Start the Celery Worker in a new terminal window ---
echo "Starting Celery worker in a new window..."
Start-Process powershell -ArgumentList "-NoExit", "-Command", "celery -A codingplatform worker -l info --pool=solo"

# --- 3. Start the Django Server in the current window ---
echo "Starting Django development server..."
python manage.py runserver