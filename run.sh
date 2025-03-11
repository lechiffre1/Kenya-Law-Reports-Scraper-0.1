#!/bin/bash
# run-scraper.sh - Script to run the Kenya Law Reports scraper

# Change to the directory containing this script
cd "$(dirname "$0")"

# Configuration
OUTPUT_DIR="KLR"
LOG_DIR="$OUTPUT_DIR/logs"
TIMESTAMP=$(date +"%Y%m%d-%H%M%S")
SCRAPER_SCRIPT="klr-scraper-optimized.py"
MAX_CONTINUOUS_RUNTIME=4800  # 80 minutes in seconds
SLEEP_BETWEEN_RUNS=1800      # 30 minutes in seconds

# Create necessary directories
mkdir -p "$OUTPUT_DIR"
mkdir -p "$LOG_DIR"

# Function to check for internet connectivity
check_internet() {
    wget -q --spider https://new.kenyalaw.org
    return $?
}

# Function to handle CTRL+C
handle_interrupt() {
    echo "[$(date)] Script interrupted by user"
    exit 1
}

# Set up the interrupt handler
trap handle_interrupt SIGINT

# Main scraping function
run_scraper() {
    local start_time=$(date +%s)
    local log_file="$LOG_DIR/scraper_$TIMESTAMP.log"
    
    echo "[$(date)] Starting scraping run. Logs at $log_file"
    
    # Run the scraper with timeout to prevent infinite runs
    timeout $MAX_CONTINUOUS_RUNTIME python3 "$SCRAPER_SCRIPT" --output "$OUTPUT_DIR" "$@" 2>&1 | tee -a "$log_file"
    
    local status=${PIPESTATUS[0]}
    local end_time=$(date +%s)
    local runtime=$((end_time - start_time))
    
    echo "[$(date)] Scraping run completed in $runtime seconds with status $status"
    
    if [ $status -eq 124 ]; then
        echo "[$(date)] Scraper timed out after $MAX_CONTINUOUS_RUNTIME seconds"
    elif [ $status -ne 0 ]; then
        echo "[$(date)] Scraper exited with error code $status"
    fi
    
    # Return scraper exit status
    return $status
}

# Check for requirements
command -v python3 >/dev/null 2>&1 || { echo "Python 3 is required but not installed. Aborting."; exit 1; }
command -v pip3 >/dev/null 2>&1 || { echo "pip3 is required but not installed. Aborting."; exit 1; }

# Install required packages if needed
if ! pip3 freeze | grep -q "beautifulsoup4"; then
    echo "Installing required Python packages..."
    pip3 install requests beautifulsoup4 tqdm
fi

# Parse command line arguments
SCRAPER_ARGS=""
NO_LOOP=false

for arg in "$@"; do
    case $arg in
        --no-loop)
            NO_LOOP=true
            ;;
        *)
            SCRAPER_ARGS="$SCRAPER_ARGS $arg"
            ;;
    esac
done

# Initial run
if check_internet; then
    run_scraper $SCRAPER_ARGS
    LAST_STATUS=$?
else
    echo "[$(date)] No internet connection. Waiting..."
    sleep 300  # Wait 5 minutes
    LAST_STATUS=1
fi

# If --no-loop is specified, exit after the first run
if $NO_LOOP; then
    exit $LAST_STATUS
fi

# Continuous run loop
while true; do
    # Check if we've scraped everything
    if [ -f "$OUTPUT_DIR/summary.json" ]; then
        if grep -q '"failed": 0' "$OUTPUT_DIR/summary.json" && \
           grep -q '"errors": 0' "$OUTPUT_DIR/summary.json"; then
            echo "[$(date)] Scraping completed successfully! Exiting."
            exit 0
        fi
    fi
    
    # Wait between runs
    echo "[$(date)] Waiting $SLEEP_BETWEEN_RUNS seconds before next run..."
    sleep $SLEEP_BETWEEN_RUNS
    
    # Update timestamp for new log file
    TIMESTAMP=$(date +"%Y%m%d-%H%M%S")
    
    # Check internet and run again
    if check_internet; then
        run_scraper $SCRAPER_ARGS
        LAST_STATUS=$?
    else
        echo "[$(date)] No internet connection. Waiting..."
        sleep 300  # Wait 5 minutes
    fi
done
