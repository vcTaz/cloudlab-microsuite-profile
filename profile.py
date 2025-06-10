"""
A CloudLab profile to measure process-level idleness of HDSearch
from the MicroSuites (μSuite) benchmark suite.

Instructions:
1. Create a new CloudLab experiment with this profile.
2. After the experiment is ready, SSH into the node.
3. The `run_experiment.sh` script will automatically execute.
4. Once completed, the results will be in /local/results.tar.gz and automatically
   copied back to your CloudLab experiment directory (accessible via the "List Nodes" page).
"""

import rspec
import geni.aggregate.cloudlab
import geni.portal as portal

# Create a Request object to build the RSpec
pc = portal.Context()

# Add a bare-metal node for direct hardware access and accurate measurements
node = pc.RawPC("node")
node.hardware_type("c8220") # A common bare-metal node type on CloudLab.
                            # Other options: r320, d430, etc.

# Specify the disk image
node.disk_image("urn:publicid:IDN+emulab.net+image+emulab/ubuntu2204")

# Add a blockstore to automatically format and mount /dev/sda4 to /mnt/newdata
# This replaces the need for mkfs.ext4 and mount in your script.
bs = node.Blockstore("data_disk", "/mnt/newdata")
bs.size = "20GB" # Adjust size as needed for MicroSuite and logs

# --- Install essential packages ---
# Docker, Git, Curl, Unzip are for MicroSuite setup
# sysstat for iostat
# linux-tools-* for perf, turbostat
# msr-tools for rdmsr/wrmsr, potentially used by pcm-power
node.addService(rspec.Install(package_contents='''
apt update && \
DEBIAN_FRONTEND=noninteractive apt install -y \
    docker.io \
    git \
    curl \
    unzip \
    sysstat \
    linux-tools-common \
    linux-tools-generic \
    linux-tools-$(uname -r) \
    msr-tools \
    numactl \
    build-essential \
    libjson-c-dev \
    lm-sensors \
    iputils-ping \
    vim
'''))

# --- Create and deploy the experiment script ---
# The script will be created on the node at /users/taz/run_experiment.sh
node.addService(rspec.Execute(shell="bash", command="""
# Ensure the /mnt/newdata permissions are correct after automatic mount
chmod -R 777 /mnt/newdata

# Increase perf_event_paranoid to allow unprivileged users to use perf
# Or set to -1 for full access by root (which our script runs as)
echo -1 | tee /proc/sys/kernel/perf_event_paranoid

# Load msr module for turbostat and direct MSR access
modprobe msr

# Create the experiment script on the node
cat <<'EOF' > /users/taz/run_experiment.sh
#!/bin/bash

# Exit immediately if a command exits with a non-zero status.
set -e

LOG_DIR="/local/results"
mkdir -p "$LOG_DIR"
chmod 777 "$LOG_DIR" # Ensure logs can be written

echo "--- Starting experiment at $(date) ---" | tee -a $LOG_DIR/experiment_log.txt

# --- 1. Docker and MicroSuite Setup ---
echo "1. Installing Docker and Cloning MicroSuite..." | tee -a $LOG_DIR/experiment_log.txt
systemctl enable docker
systemctl start docker
systemctl status docker --no-pager # Verify docker is running

cd /mnt/newdata
git clone https://github.com/svassi04/MicroSuite.git || { echo "MicroSuite clone failed, already exists or other error. Continuing..." && cd MicroSuite; }
cd MicroSuite

# The setup_node_mydata.sh script typically handles Docker image builds.
# It might run docker compose. Let's ensure it completes.
echo "Running MicroSuite setup_node_mydata.sh..." | tee -a $LOG_DIR/experiment_log.txt
chmod +x setup_node_mydata.sh
# ./setup_node_mydata.sh # This script might run docker compose up -d directly
# For clarity, let's explicitly run docker compose after setup if needed.
# Check MicroSuite's documentation for exact setup_node_mydata.sh behavior.

# Assuming setup_node_mydata.sh builds/prepares. Now explicitly run docker compose up.
echo "Running docker compose up -d..." | tee -a $LOG_DIR/experiment_log.txt
docker compose up -d --build # --build ensures images are fresh

# Give services some time to start
echo "Waiting for Docker containers to settle..." | tee -a $LOG_DIR/experiment_log.txt
sleep 30

# --- 2. Identify HDSearch Container PID ---
# You may need to inspect MicroSuite's docker-compose.yml to find the exact service name
# For HDSearch, it's often 'hdsearch' or similar.
# Let's assume the service name is 'hdsearch' and container name pattern is 'microsuite-hdsearch-1'
HDS_CONTAINER_NAME=$(docker ps --format "{{.Names}}" | grep "hdsearch" | head -n 1)
if [ -z "$HDS_CONTAINER_NAME" ]; then
    echo "ERROR: HDSearch container not found. Check docker-compose.yml service names." | tee -a $LOG_DIR/experiment_log.txt
    docker ps -a | tee -a $LOG_DIR/experiment_log.txt
    exit 1
fi
echo "Identified HDSearch container: $HDS_CONTAINER_NAME" | tee -a $LOG_DIR/experiment_log.txt
HDS_PID=$(docker inspect --format '{{.State.Pid}}' "$HDS_CONTAINER_NAME")

if [ -z "$HDS_PID" ]; then
    echo "ERROR: Could not get PID for HDSearch container. Exiting." | tee -a $LOG_DIR/experiment_log.txt
    exit 1
fi
echo "HDSearch Container PID: $HDS_PID" | tee -a $LOG_DIR/experiment_log.txt

# --- 3. Start Background Monitoring Tools ---
echo "3. Starting profiling tools..." | tee -a $LOG_DIR/experiment_log.txt

# perf stat for CPU idleness, stalls, cache, context switches
# -a: system-wide
# -p $HDS_PID: process-level (focus on HDSearch)
# -I 100: interval of 100ms
# Add common events related to idleness and efficiency
perf stat -a -I 100 -e \
    cycles,instructions,stalled-cycles-frontend,stalled-cycles-backend,\
    cache-references,cache-misses,L1-dcache-load-misses,LLC-load-misses,\
    dTLB-load-misses,iTLB-load-misses,bus-cycles,\
    context-switches,cpu-migrations \
    -o "$LOG_DIR/perf_system_summary.log" &
PERF_SYSTEM_PID=$!
echo "perf system started with PID $PERF_SYSTEM_PID" | tee -a $LOG_DIR/experiment_log.txt

perf stat -p "$HDS_PID" -I 100 -e \
    cycles,instructions,stalled-cycles-frontend,stalled-cycles-backend,\
    cache-references,cache-misses,L1-dcache-load-misses,LLC-load-misses,\
    dTLB-load-misses,iTLB-load-misses,bus-cycles,\
    context-switches,cpu-migrations \
    -o "$LOG_DIR/perf_hdsearch_process.log" &
PERF_PROCESS_PID=$!
echo "perf process started with PID $PERF_PROCESS_PID" | tee -a $LOG_DIR/experiment_log.txt


# turbostat for C-states and Package Watt
# -i 1: interval 1 second
# -q: quiet (no header at each interval)
# --debug: to get more detailed power info if available
turbostat -i 1 --debug -q -o "$LOG_DIR/turbostat_output.log" &
TURBOSTAT_PID=$!
echo "turbostat started with PID $TURBOSTAT_PID" | tee -a $LOG_DIR/experiment_log.txt

# iostat for I/O latency
# -x: extended statistics
# -d: device utilization
# 1: interval 1 second
iostat -x -d 1 > "$LOG_DIR/iostat_output.log" &
IOSTAT_PID=$!
echo "iostat started with PID $IOSTAT_PID" | tee -a $LOG_DIR/experiment_log.txt

# powercap for DRAM Watt (assuming Intel RAPL interface)
# This will log energy in microjoules, calculate delta for Watts.
# intel-rapl:0 is the package, intel-rapl:0:1 is typically DRAM on modern Intel CPUs
PACKAGE_RAPL_PATH="/sys/class/powercap/intel-rapl/intel-rapl:0/energy_uj"
DRAM_RAPL_PATH="/sys/class/powercap/intel-rapl/intel-rapl:0:1/energy_uj"
if [ -f "$PACKAGE_RAPL_PATH" ] && [ -f "$DRAM_RAPL_PATH" ]; then
    echo "Collecting powercap data..." | tee -a $LOG_DIR/experiment_log.txt
    (
        echo "Timestamp,Package_uJ,DRAM_uJ"
        while true; do
            CURRENT_TIME=$(date +%s.%N)
            PACKAGE_ENERGY=$(cat "$PACKAGE_RAPL_PATH")
            DRAM_ENERGY=$(cat "$DRAM_RAPL_PATH")
            echo "$CURRENT_TIME,$PACKAGE_ENERGY,$DRAM_ENERGY"
            sleep 1 # Sample every second
        done
    ) > "$LOG_DIR/powercap_output.csv" &
    POWERCAP_PID=$!
    echo "powercap script started with PID $POWERCAP_PID" | tee -a $LOG_DIR/experiment_log.txt
else
    echo "WARNING: Intel RAPL powercap paths not found, skipping DRAM/Package powercap collection." | tee -a $LOG_DIR/experiment_log.txt
fi

echo "Giving monitors a moment to start..." | tee -a $LOG_DIR/experiment_log.txt
sleep 5 # Give background processes time to initialize

# --- 4. Execute HDSearch Benchmark ---
echo "4. Executing HDSearch benchmark..." | tee -a $LOG_DIR/experiment_log.txt
# This is the crucial part: You need to know the exact command to run HDSearch
# within its Docker container.
# Example: docker exec <container_name> /path/to/hdsearch_binary <arguments>
# Consult MicroSuite's documentation or Dockerfile for HDSearch.
# For example, it might be something like:
# docker exec "$HDS_CONTAINER_NAME" /usr/local/bin/hdsearch --workload A --size 1GB --iterations 10
# Or, if MicroSuite has a specific 'run' script:
# docker exec "$HDS_CONTAINER_NAME" /bin/bash -c "cd /app && ./run_hdsearch.sh"
#
# Placeholder command:
# Let's assume a simple /usr/local/bin/hdsearch exists in the container
# If HDSearch has specific arguments like workload, size, etc., add them here.
# For robust testing, consider running it for a fixed duration or number of operations.
#
# IMPORTANT: Replace the following line with the actual command to run HDSearch
# within the Docker container.
echo "Running dummy sleep for HDSearch (REPLACE THIS WITH ACTUAL HDSearch COMMAND!)" | tee -a $LOG_DIR/experiment_log.txt
docker exec "$HDS_CONTAINER_NAME" bash -c "sleep 60 && echo 'HDSearch placeholder completed'" 2>&1 | tee -a "$LOG_DIR/hdsearch_execution.log"

echo "HDSearch execution completed." | tee -a $LOG_DIR/experiment_log.txt

# --- 5. Stop Monitoring Tools ---
echo "5. Stopping profiling tools..." | tee -a $LOG_DIR/experiment_log.txt
kill -SIGINT $PERF_SYSTEM_PID || true
kill -SIGINT $PERF_PROCESS_PID || true
kill -SIGINT $TURBOSTAT_PID || true
kill -SIGINT $IOSTAT_PID || true
if [ -n "$POWERCAP_PID" ]; then # Only kill if it was started
    kill -SIGINT $POWERCAP_PID || true
fi

# Give them a moment to write out remaining data
echo "Waiting for monitors to finish writing logs..." | tee -a $LOG_DIR/experiment_log.txt
sleep 5

# --- 6. Collect and Package Results ---
echo "6. Archiving results..." | tee -a $LOG_DIR/experiment_log.txt
tar -czf "/local/results.tar.gz" -C "/local" "results"
echo "Results archived to /local/results.tar.gz" | tee -a $LOG_DIR/experiment_log.txt

# --- Cleanup Docker containers (optional, but good practice) ---
echo "Cleaning up Docker containers..." | tee -a $LOG_DIR/experiment_log.txt
docker compose down --volumes --rmi all || true

echo "--- Experiment completed at $(date) ---" | tee -a $LOG_DIR/experiment_log.txt
EOF

# Make the script executable
chmod +x /users/taz/run_experiment.sh

# Run the experiment script
/users/taz/run_experiment.sh 2>&1 | tee /local/experiment_full_output.log

# Ensure the results directory and archive are readable by CloudLab's
# file transfer mechanism.
chmod -R 777 /local/results
chmod 644 /local/results.tar.gz
"""))

# Automatically copy the results directory back to the CloudLab experiment
# by specifying a source filesystem.
pc.defineParameter(
    "source_fs",
    "Source Filesystem",
    portal.ParameterType.STRING,
    "/local", # This tells CloudLab to copy everything from /local
    longDescription="The path on the node where experiment results are stored (for automatic retrieval)."
)

# Print the RSpec
pc.printRequest(pc.make*/)
