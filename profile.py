# Import the Portal object.
import geni.portal as portal
# Import the ProtoGENI library.
import geni.rspec.pg as pg
# Emulab specific extensions.
import geni.rspec.emulab as emulab

# Create a portal context, needed to defined parameters
pc = portal.Context()

# Create a Request object to start building the RSpec.
request = pc.makeRequestRSpec()

# Experiment-specific parameters
pc.defineParameter("nodeCount", "Number of Nodes", portal.ParameterType.INTEGER, 1,
                    longDescription="For this experiment, we recommend a single node.")

pc.defineParameter("osImage", "Select OS image",
                    portal.ParameterType.IMAGE,
                    'urn:publicid:IDN+emulab.net+image+emulab-ops//UBUNTU20-64-STD', # Recommended for good tool support
                    [
                        ('urn:publicid:IDN+emulab.net+image+emulab-ops//UBUNTU20-64-STD', 'UBUNTU 20.04'),
                        ('urn:publicid:IDN+emulab.net+image+emulab-ops//UBUNTU22-64-STD', 'UBUNTU 22.04'), # If available
                        ('default', 'Default Image'), # Fallback
                    ],
                    longDescription="Choose a recent Ubuntu image for best compatibility with profiling tools.")

pc.defineParameter("phystype", "Optional physical node type",
                    portal.ParameterType.STRING, "d430", # Example: A node type known to have good Intel CPU features
                    longDescription="Specify a physical node type (e.g., d430, xl170) " +
                    "to ensure access to advanced CPU features for profiling.")

pc.defineParameter("runTime", "HDSearch Benchmark Run Time (seconds)",
                    portal.ParameterType.INTEGER, 300,
                    longDescription="Duration in seconds for which HDSearch will run and metrics will be collected.")

pc.defineParameter("profileInterval", "Profiling Interval (milliseconds)",
                    portal.ParameterType.INTEGER, 1000,
                    longDescription="Interval at which `perf` and `iostat` will sample data (in milliseconds).")

# Optional parameters for advanced control
pc.defineParameter("tempFileSystemSize", "Temporary Filesystem Size (GB)",
                    portal.ParameterType.INTEGER, 100, advanced=True,
                    longDescription="The size in GB of a temporary file system to mount on each of your " +
                    "nodes. Use this if you expect you will need more space for data or tools.")

pc.defineParameter("tempFileSystemMount", "Temporary Filesystem Mount Point",
                    portal.ParameterType.STRING, "/mydata", advanced=True,
                    longDescription="Mount the temporary file system at this mount point.")


# Retrieve the values the user specifies during instantiation.
params = pc.bindParameters()

# Check parameter validity.
if params.nodeCount != 1:
    pc.reportError(portal.ParameterError("This experiment is designed for a single node.", ["nodeCount"]))

if params.tempFileSystemSize < 0 or params.tempFileSystemSize > 500: # Increased max size
    pc.reportError(portal.ParameterError("Please specify a size greater then zero and " +
                                          "less then 500GB", ["tempFileSystemSize"]))

if params.runTime <= 0:
    pc.reportError(portal.ParameterError("Run time must be greater than zero.", ["runTime"]))

if params.profileInterval <= 0:
    pc.reportError(portal.ParameterError("Profiling interval must be greater than zero.", ["profileInterval"]))

pc.verifyParameters()

# Create a single node
name = "hdsearch-node"
node = request.RawPC(name)

# Set OS image
if params.osImage and params.osImage != "default":
    node.disk_image = params.osImage

# Set physical type
if params.phystype != "":
    node.hardware_type = params.phystype

# Optional Blockstore
if params.tempFileSystemSize > 0:
    bs = node.Blockstore(name + "-bs", params.tempFileSystemMount)
    bs.size = str(params.tempFileSystemSize) + "GB"
    bs.placement = "any"

# --- Startup Script for Experiment Setup and Data Collection ---
node.addService(pg.Execute(shell="bash", command="""
# Log file location
LOG_DIR="/mydata/hdsearch_experiment_logs"
mkdir -p $LOG_DIR
cd /mydata

# --- Add more storage if needed (already handled by blockstore, but good to have checks) ---
# Check if /dev/sda4 exists and mount it if not already mounted
if [ -b /dev/sda4 ] && ! grep -qs '/mnt/newdata' /proc/mounts; then
    echo "Found /dev/sda4, mounting it..."
    sudo mkfs.ext4 -F /dev/sda4 # Force overwrite if already formatted
    sudo mkdir -p /mnt/newdata
    sudo mount /dev/sda4 /mnt/newdata
    echo "/dev/sda4 /mnt/newdata ext4 defaults 0 0" | sudo tee -a /etc/fstab
    sudo chmod -R 777 /mnt/newdata/
    cd /mnt/newdata/
else
    echo "/dev/sda4 not found or already mounted. Proceeding with /mydata."
    cd /mydata/
fi

# Give permissions to the new storage (if /mydata is used, it already has permissions)
sudo chmod -R 777 .

# --- Clone MicroSuite Git Repository ---
echo "Cloning MicroSuite repository..."
if [ ! -d "MicroSuite" ]; then
    git clone https://github.com/svassi04/MicroSuite.git
    cd MicroSuite
else
    echo "MicroSuite directory already exists. Pulling latest changes..."
    cd MicroSuite
    git remote add fork https://github.com/svassi04/MicroSuite.git || true # Add if not exists
    git fetch fork
    git config --global user.name "cloudlab_user" # Replace with a generic username
    git config --global user.email "cloudlab_user@example.com" # Replace with a generic email
    git stash save "Stash before merging from fork" || true # Stash if there are local changes
    git merge fork/master
fi

# --- Install necessary dependencies and Run MicroSuite ---
echo "Installing MicroSuite dependencies and starting Docker services..."
sudo sh setup_node_mydata.sh
sudo docker compose up -d

# Get container ID for MicroSuite (assuming it's the only one or identifiable)
CONTAINER_ID=$(sudo docker ps -q --filter ancestor=microsuite_microservice | head -n 1)

if [ -z "$CONTAINER_ID" ]; then
    echo "ERROR: Could not find MicroSuite Docker container ID. Exiting."
    exit 1
fi

echo "MicroSuite Docker container ID: $CONTAINER_ID"

# --- Install Profiling Tools ---
echo "Installing profiling tools..."
sudo apt-get update -y
sudo apt-get install -y linux-tools-$(uname -r) linux-tools-generic perf-tools-unstable iostat sysstat msr-tools numactl stress-ng # msr-tools for turbostat/powercap

# --- Prepare for power measurements (turbostat, powercap, pcm-power) ---
# turbostat is usually part of linux-tools-generic.
# For powercap, ensure the kernel module is loaded (often automatic).
# pcm-power requires Intel PCM, which might need building. Let's provide instructions if manual install is needed.
# For simplicity in automated setup, we'll focus on turbostat and perf for power initially.

# Load msr kernel module for turbostat/powercap
sudo modprobe msr

# Ensure intel_rapl is loaded for powercap (often automatic)
sudo modprobe intel_rapl || true

# --- Run HDSearch benchmark and collect metrics ---
echo "Starting HDSearch benchmark and collecting idleness metrics..."

# Define benchmark command (assuming HDSearch is accessible within the container)
# You might need to adjust this command based on how HDSearch is run inside the container.
# Example: If HDSearch is an executable at /app/hdsearch within the container
HDS_COMMAND="sudo docker exec $CONTAINER_ID bash -c 'cd /MicroSuite && ./MicroSuite-benchmarks/build/bin/HDSearch'" # Adjust path/command as needed

# Ensure the HDSearch command is actually runnable inside the container
sudo docker exec $CONTAINER_ID bash -c 'cd /MicroSuite && ls -l MicroSuite-benchmarks/build/bin/HDSearch' || { echo "ERROR: HDSearch executable not found in container. Please verify path."; exit 1; }

# CPU wait time and Context Switching with perf
# `perf stat -e cpu-cycles,instructions,task-clock,context-switches,cpu-migrations,major-faults,minor-faults -a -o $LOG_DIR/perf_stat.log -- $HDS_COMMAND`
# `perf record -F ${params.profileInterval} -e instructions,cpu-cycles,cache-references,cache-misses,page-faults,sched:sched_switch,power:energy-pkg,power:energy-dram -a -g -o $LOG_DIR/perf_record.data -- $HDS_COMMAND`
# For idleness, sched:sched_switch is useful, and general CPU utilization from `perf stat`.
# More direct idleness metrics: `idle-cycles`, `stalled-cycles-frontend`, `stalled-cycles-backend`
echo "Collecting perf stat data..."
sudo perf stat -e cpu-cycles,instructions,task-clock,context-switches,cpu-migrations,major-faults,minor-faults,stalled-cycles-frontend,stalled-cycles-backend -a -o $LOG_DIR/perf_stat.log -- $HDS_COMMAND &
PERF_STAT_PID=$!

echo "Collecting perf record data (background)..."
sudo perf record -F 99 -e cpu-cycles,instructions,cache-references,cache-misses,page-faults,sched:sched_switch,power:energy-pkg,power:energy-dram -a -g -o $LOG_DIR/perf_record.data -- sleep ${params.runTime} &
PERF_RECORD_PID=$!

# Memory stalls, I/O latency with iostat
echo "Collecting iostat data..."
iostat -xc -d 1 > $LOG_DIR/iostat.log &
IOSTAT_PID=$!

# CPU C-states and Power measurements (Package Watt, DRAM Watt) with turbostat
echo "Collecting turbostat data..."
# turbostat -S 1 -q -o $LOG_DIR/turbostat.log --msr --show-cstate --show-cpu-power --show-dram-power --show-package-power -- $HDS_COMMAND
# turbostat can conflict if perf is trying to measure power events.
# Let's run turbostat for a fixed duration if the benchmark is run directly by `perf stat`.
# Or, if `perf stat` captures power, we can rely on that.
# For simplicity, we'll run turbostat for the same duration as the benchmark.
sudo turbostat --cpu ALL --quiet --msr --show-cstate --show-pkg-temp --show-pkg-power --show-dram-power --interval 1 --num_iterations ${params.runTime} > $LOG_DIR/turbostat.log 2>&1 &
TURBOSTAT_PID=$!


# Optional: Emulate disaggregated memory access patterns
# This part is more complex and depends on your specific setup.
# You could use `stress-ng` with memory access patterns or `numactl` to pin processes to specific NUMA nodes
# and then use `latency injection` tools (e.g., netem for network latency, but memory access is harder)
# or `memory throttling` (e.g., via cgroups or custom kernel modules).
# For now, this is a placeholder.
# echo "Emulating disaggregated memory (optional, not implemented in this script)..."
# You might need to pause the benchmark, apply memory latency/throttling, then resume.
# This would likely involve a more complex orchestrator script.

echo "Waiting for benchmark and profiling to complete..."
# Wait for the HDSearch command started by perf stat to finish (or the perf record sleep to finish)
wait $PERF_STAT_PID
wait $PERF_RECORD_PID
kill $IOSTAT_PID
kill $TURBOSTAT_PID

# Ensure all background processes are terminated gracefully
sudo pkill -SIGINT iostat
sudo pkill -SIGINT turbostat

# Process perf data
echo "Processing perf data..."
sudo perf script -i $LOG_DIR/perf_record.data > $LOG_DIR/perf_script.log 2>&1

# --- Log and Export Collected Metrics ---
echo "Archiving collected logs..."
tar -czvf /mydata/hdsearch_idleness_logs_$(hostname)_$(date +%Y%m%d-%H%M%S).tar.gz -C /mydata/ hdsearch_experiment_logs
echo "Experiment completed. Logs are in /mydata/hdsearch_idleness_logs_*.tar.gz"

# Stop MicroSuite Docker containers (optional, if you want to clean up after experiment)
echo "Stopping MicroSuite Docker containers..."
sudo docker compose down
"""))

# Print the RSpec to the enclosing page.
pc.printRequestRSpec(request)