You're getting an `ImportError: No module named rspec` because `rspec` itself is not a standalone Python module you import directly.

The components like `Install` and `Execute` services are part of the `geni.rspec.pg` submodule, which you've already imported as `pg` (i.e., `import geni.rspec.pg as pg`).

The line causing the issue is:
`import rspec # For clarity with rspec.Install, rspec.Execute etc.`

You don't need this line. Instead, you should use `pg.Install` and `pg.Execute` since `pg` is the alias for `geni.rspec.pg`.

**Here's how to fix it:**

1.  **Remove** the line `import rspec # For clarity with rspec.Install, rspec.Execute etc.`
2.  **Change** all occurrences of `rspec.Install` to `pg.Install`.
3.  **Change** all occurrences of `rspec.Execute` to `pg.Execute`.

Here's the corrected `profile.py`:

```python
#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
A CloudLab profile to measure process-level idleness of HDSearch
from the MicroSuites (μSuite) benchmark suite.

This profile extends a generic multi-node setup to dedicate the first node
to the HDSearch experiment with detailed profiling and power measurements.

Instructions:
1. Create a new CloudLab experiment with this profile.
2. The experiment is designed to run automatically on the first allocated node.
3. Once the experiment completes (which might take 10-20 minutes depending on HDSearch run time),
   the results will be in /local/results.tar.gz on the `hdsearch-node` and automatically
   copied back to your CloudLab experiment directory (accessible via the "List Nodes" page).
4. You can SSH into the node to check progress via /local/experiment_full_output.log
   or inspect the collected files in /local/results/ before the experiment ends.
"""

# Import the Portal object.
import geni.portal as portal
# Import the ProtoGENI library.
import geni.rspec.pg as pg # This imports pg, which contains Install and Execute
# Emulab specific extensions.
import geni.rspec.emulab as emulab
# REMOVED: import rspec # This line caused the ImportError

# Create a portal context, needed to defined parameters
pc = portal.Context()

# Create a Request object to start building the RSpec.
request = pc.makeRequestRSpec()

# --- Parameters for HDSearch Experiment (defaults set for optimal HDSearch setup) ---
# Default nodeCount to 1 as the HDSearch experiment is single-node focused.
pc.defineParameter("nodeCount", "Number of Nodes", portal.ParameterType.INTEGER, 1,
                   longDescription="For the HDSearch experiment, 1 node is typically sufficient. " +
                   "If you specify more than one node, only the first node will be configured for HDSearch.")

# Force a specific OS image for the HDSearch node (Ubuntu 22.04 recommended for tools).
# The user's list has default, but we'll override for node0.
pc.defineParameter("osImage", "Select OS image",
                   portal.ParameterType.IMAGE,
                   'urn:publicid:IDN+emulab.net+image+emulab/ubuntu2204', # Default to Ubuntu 22.04 for HDSearch
                   [('default', 'Default Image'),
                    ('urn:publicid:IDN+emulab.net+image+emulab-ops//UBUNTU18-64-STD', 'UBUNTU 18.04'),
                    ('urn:publicid:IDN+emulab.net+image+emulab-ops//UBUNTU20-64-STD', 'UBUNTU 20.04'),
                    ('urn:publicid:IDN+emulab.net+image+emulab-ops//UBUNTU22-64-STD', 'UBUNTU 22.04'), # Explicitly added
                    ('urn:publicid:IDN+emulab.net+image+emulab-ops//CENTOS7-64-STD',  'CENTOS 7'),
                    ('urn:publicid:IDN+emulab.net+image+emulab-ops//CENTOS8-64-STD',  'CENTOS 8'),
                    ('urn:publicid:IDN+emulab.net+image+emulab-ops//FBSD114-64-STD', 'FreeBSD 11.4'),
                    ('urn:publicid:IDN+emulab.net+image+emulab-ops//FBSD122-64-STD', 'FreeBSD 12.2')],
                   longDescription="For HDSearch, Ubuntu 22.04 is recommended. " +
                   "The first node will use this image regardless of selection if specific for HDSearch.")

# Force a specific hardware type for the HDSearch node (c8220 recommended for perf/power access).
pc.defineParameter("phystype",  "Optional physical node type",
                   portal.ParameterType.STRING, "c8220", # Default to c8220 for HDSearch
                   longDescription="Specify a physical node type (pc3000,d710,c8220,etc). " +
                   "For HDSearch, c8220 is recommended for performance monitoring access. " +
                   "The first node will attempt to use this type.")

# Force bare-metal nodes for the HDSearch experiment (VMs might hide hardware details).
pc.defineParameter("useVMs",  "Use XEN VMs",
                   portal.ParameterType.BOOLEAN, False,
                   longDescription="For accurate HDSearch performance measurement, bare metal nodes are required. " +
                   "This option is ignored for the first node if it's running HDSearch.")

# Parameter for results retrieval
pc.defineParameter(
    "source_fs",
    "Source Filesystem for Results",
    portal.ParameterType.STRING,
    "/local", # This tells CloudLab to copy everything from /local
    longDescription="The path on the node where experiment results are stored (for automatic retrieval)."
)

# --- Generic Parameters from the user's original template ---
pc.defineParameter("startVNC",  "Start X11 VNC on your nodes",
                   portal.ParameterType.BOOLEAN, False,
                   longDescription="Start X11 VNC server on your nodes. There will be " +
                   "a menu option in the node context menu to start a browser based VNC " +
                   "client. Works really well, give it a try!")
pc.defineParameter("linkSpeed", "Link Speed",portal.ParameterType.INTEGER, 0,
                   [(0,"Any"),(100000,"100Mb/s"),(1000000,"1Gb/s"),(10000000,"10Gb/s"),(25000000,"25Gb/s"),(100000000,"100Gb/s")],
                   advanced=True,
                   longDescription="A specific link speed to use for your lan. Normally the resource " +
                   "mapper will choose for you based on node availability and the optional physical type.")
pc.defineParameter("bestEffort",  "Best Effort", portal.ParameterType.BOOLEAN, False,
                    advanced=True,
                    longDescription="For very large lans, you might get an error saying 'not enough bandwidth.' " +
                    "This options tells the resource mapper to ignore bandwidth and assume you know what you " +
                    "are doing, just give me the lan I ask for (if enough nodes are available).")
pc.defineParameter("sameSwitch",  "No Interswitch Links", portal.ParameterType.BOOLEAN, False,
                    advanced=True,
                    longDescription="Sometimes you want all the nodes connected to the same switch. " +
                    "This option will ask the resource mapper to do that, although it might make " +
                    "it imppossible to find a solution. Do not use this unless you are sure you need it!")
pc.defineParameter("tempFileSystemSize", "Temporary Filesystem Size",
                   portal.ParameterType.INTEGER, 0,advanced=True,
                   longDescription="The size in GB of a temporary file system to mount on each of your " +
                   "nodes. Temporary means that they are deleted when your experiment is terminated. " +
                   "The images provided by the system have small root partitions, so use this option " +
                   "if you expect you will need more space to build your software packages or store " +
                   "temporary files.")
pc.defineParameter("tempFileSystemMax",  "Temp Filesystem Max Space",
                    portal.ParameterType.BOOLEAN, False,
                    advanced=True,
                    longDescription="Instead of specifying a size for your temporary filesystem, " +
                    "check this box to allocate all available disk space. Leave the size above as zero.")
pc.defineParameter("tempFileSystemMount", "Temporary Filesystem Mount Point",
                   portal.ParameterType.STRING,"/mydata",advanced=True,
                   longDescription="Mount the temporary file system at this mount point; in general you " +
                   "you do not need to change this, but we provide the option just in case your software " +
                   "is finicky.")


# Retrieve the values the user specifies during instantiation.
params = pc.bindParameters()

# Check parameter validity.
if params.nodeCount < 1:
    pc.reportError(portal.ParameterError("You must choose at least 1 node.", ["nodeCount"]))

if params.tempFileSystemSize < 0 or params.tempFileSystemSize > 200:
    pc.reportError(portal.ParameterError("Please specify a size greater then zero and " +
                                         "less then 200GB", ["nodeCount"]))
pc.verifyParameters()

# Create link/lan (only if more than 1 node).
if params.nodeCount > 1:
    if params.nodeCount == 2:
        lan = request.Link()
    else:
        lan = request.LAN()
        pass
    if params.bestEffort:
        lan.best_effort = True
    elif params.linkSpeed > 0:
        lan.bandwidth = params.linkSpeed
    if params.sameSwitch:
        lan.setNoInterSwitchLinks()
    pass

# Process nodes, adding to link or lan.
for i in range(params.nodeCount):
    # Create the first node (node0) specifically for HDSearch
    if i == 0:
        name = "hdsearch-node"
        node = request.RawPC(name) # Force bare metal for accurate profiling
        node.hardware_type = params.phystype # Use the selected phystype (defaults to c8220)
        node.disk_image = params.osImage     # Use the selected osImage (defaults to Ubuntu 22.04)

        # Add a blockstore to automatically format and mount /dev/sda4 to /mnt/newdata
        # This is crucial for MicroSuite setup and Docker storage.
        bs = node.Blockstore("data_disk", "/mnt/newdata")
        bs.size = "20GB" # Adjust size as needed for MicroSuite and logs
        bs.placement = "any" # CloudLab will find space anywhere

        # Install essential packages for HDSearch experiment and profiling tools
        node.addService(pg.Install(package_contents='''
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

        # Create and deploy the experiment script (`run_experiment.sh`)
        node.addService(pg.Execute(shell="bash", command="""
# Ensure the /mnt/newdata permissions are correct after automatic mount
chmod -R 777 /mnt/newdata

# Increase perf_event_paranoid to allow unprivileged users to use perf
# -1 for full access by root (which our script runs as)
echo -1 | tee /proc/sys/kernel/perf_event_paranoid

# Load msr module for turbostat and direct MSR access (Intel RAPL)
modprobe msr || true # '|| true' to prevent script from failing if already loaded or module not found

# Create the experiment script on the node
cat <<'EOF_SCRIPT' > /users/taz/run_experiment.sh
#!/bin/bash

# Exit immediately if a command exits with a non-zero status.
set -e

LOG_DIR="/local/results"
mkdir -p "$LOG_DIR"
chmod 777 "$LOG_DIR" # Ensure logs can be written

echo "--- Starting HDSearch Idleness Experiment at $(date) ---" | tee -a $LOG_DIR/experiment_log.txt

# --- 1. Docker and MicroSuite Setup ---
echo "1. Installing Docker and Cloning MicroSuite..." | tee -a $LOG_DIR/experiment_log.txt
systemctl enable docker
systemctl start docker
systemctl status docker --no-pager # Verify docker is running

cd /mnt/newdata
# Clone MicroSuite, if already exists, just change directory
git clone https://github.com/svassi04/MicroSuite.git || { echo "MicroSuite clone failed or already exists. Changing directory..." && cd MicroSuite; }
cd MicroSuite

# The setup_node_mydata.sh script typically handles Docker image builds.
echo "Running MicroSuite setup_node_mydata.sh (may take a while)..." | tee -a $LOG_DIR/experiment_log.txt
chmod +x setup_node_mydata.sh
./setup_node_mydata.sh 2>&1 | tee -a $LOG_DIR/microsuite_setup.log

# Ensure containers are up and running, potentially rebuilding images
echo "Running docker compose up -d --build --force-recreate..." | tee -a $LOG_DIR/experiment_log.txt
docker compose up -d --build --force-recreate 2>&1 | tee -a $LOG_DIR/docker_compose_up.log

# Give services some time to start
echo "Waiting for Docker containers to settle (60 seconds)..." | tee -a $LOG_DIR/experiment_log.txt
sleep 60

# --- 2. Identify HDSearch Container PID ---
HDS_CONTAINER_NAME=$(docker ps --format "{{.Names}}" | grep "hdsearch" | head -n 1)
if [ -z "$HDS_CONTAINER_NAME" ]; then
    echo "ERROR: HDSearch container not found. Check docker-compose.yml service names or if it exited prematurely." | tee -a $LOG_DIR/experiment_log.txt
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
# -a: system-wide, -p $HDS_PID: process-level, -I 100: interval of 100ms
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
turbostat -i 1 --debug -q -o "$LOG_DIR/turbostat_output.log" &
TURBOSTAT_PID=$!
echo "turbostat started with PID $TURBOSTAT_PID" | tee -a $LOG_DIR/experiment_log.txt

# iostat for I/O latency
iostat -x -d 1 > "$LOG_DIR/iostat_output.log" &
IOSTAT_PID=$!
echo "iostat started with PID $IOSTAT_PID" | tee -a $LOG_DIR/experiment_log.txt

# powercap for DRAM Watt (assuming Intel RAPL interface)
PACKAGE_RAPL_PATH="/sys/class/powercap/intel-rapl/intel-rapl:0/energy_uj"
DRAM_RAPL_PATH="/sys/class/powercap/intel-rapl/intel-rapl:0:1/energy_uj"
POWERCAP_PID="" # Initialize to empty

if [ -f "$PACKAGE_RAPL_PATH" ] && [ -f "$DRAM_RAPL_PATH" ]; then
    echo "Collecting powercap data (Package and DRAM Watts)..." | tee -a $LOG_DIR/experiment_log.txt
    (
        echo "Timestamp_sec,Package_uJ,DRAM_uJ,Package_Watt,DRAM_Watt"
        # Initial read for delta calculation
        LAST_PACKAGE_ENERGY=$(cat "$PACKAGE_RAPL_PATH")
        LAST_DRAM_ENERGY=$(cat "$DRAM_RAPL_PATH")
        LAST_TIME=$(date +%s.%N)

        while true; do
            sleep 1 # Sample every second

            CURRENT_TIME=$(date +%s.%N)
            CURRENT_PACKAGE_ENERGY=$(cat "$PACKAGE_RAPL_PATH")
            CURRENT_DRAM_ENERGY=$(cat "$DRAM_RAPL_PATH")

            TIME_DELTA=$(echo "$CURRENT_TIME - $LAST_TIME" | bc -l)
            PACKAGE_DELTA_uJ=$(echo "$CURRENT_PACKAGE_ENERGY - $LAST_PACKAGE_ENERGY" | bc -l)
DRAM_DELTA_uJ=$(echo "$CURRENT_DRAM_ENERGY - $LAST_DRAM_ENERGY" | bc -l)

            # Convert uJ/s to Watts (1W = 1J/s = 1,000,000 uJ/s)
            PACKAGE_WATT=$(echo "scale=3; $PACKAGE_DELTA_uJ / ($TIME_DELTA * 1000000)" | bc -l)
            DRAM_WATT=$(echo "scale=3; $DRAM_DELTA_uJ / ($TIME_DELTA * 1000000)" | bc -l)

            echo "$CURRENT_TIME,$CURRENT_PACKAGE_ENERGY,$CURRENT_DRAM_ENERGY,$PACKAGE_WATT,$DRAM_WATT"
            
            LAST_PACKAGE_ENERGY="$CURRENT_PACKAGE_ENERGY"
            LAST_DRAM_ENERGY="$CURRENT_DRAM_ENERGY"
            LAST_TIME="$CURRENT_TIME"
        done
    ) > "$LOG_DIR/powercap_output.csv" &
    POWERCAP_PID=$!
    echo "powercap script started with PID $POWERCAP_PID" | tee -a $LOG_DIR/experiment_log.txt
else
    echo "WARNING: Intel RAPL powercap paths not found, skipping DRAM/Package powercap collection. (Is this an Intel CPU?)" | tee -a $LOG_DIR/experiment_log.txt
fi

echo "Giving monitors a moment to start (5 seconds)..." | tee -a $LOG_DIR/experiment_log.txt
sleep 5 # Give background processes time to initialize

# --- 4. Execute HDSearch Benchmark ---
echo "4. Executing HDSearch benchmark..." | tee -a $LOG_DIR/experiment_log.txt

# The MicroSuite hdsearch Dockerfile sets its working directory to /app and its CMD to ./run_hdsearch.sh.
# So, the standard way to run it within the container is via this script.
# This command will execute HDSearch and its output will be logged.
echo "Executing HDSearch via its run script (/app/run_hdsearch.sh)..." | tee -a $LOG_DIR/experiment_log.txt
docker exec "$HDS_CONTAINER_NAME" /app/run_hdsearch.sh 2>&1 | tee -a "$LOG_DIR/hdsearch_execution.log"

echo "HDSearch execution completed." | tee -a $LOG_DIR/experiment_log.txt

# Give the benchmark a moment to complete any cleanup and for tools to capture final data
sleep 10

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
echo "Waiting for monitors to finish writing logs (5 seconds)..." | tee -a $LOG_DIR/experiment_log.txt
sleep 5

# --- 6. Collect and Package Results ---
echo "6. Archiving results..." | tee -a $LOG_DIR/experiment_log.txt
# Ensure the /local/results directory exists and is accessible for archiving
mkdir -p /local/results || true
mv "$LOG_DIR"/* "/local/results/" || true # Move contents, ignore errors if LOG_DIR is empty
tar -czf "/local/results.tar.gz" -C "/local" "results"
echo "Results archived to /local/results.tar.gz" | tee -a $LOG_DIR/experiment_log.txt

# --- Cleanup Docker containers (optional, but good practice) ---
echo "Cleaning up Docker containers..." | tee -a $LOG_DIR/experiment_log.txt
docker compose down --volumes --rmi all || true

echo "--- HDSearch Idleness Experiment completed at $(date) ---" | tee -a $LOG_DIR/experiment_log.txt
EOF_SCRIPT

# Make the script executable
chmod +x /users/taz/run_experiment.sh

# Run the experiment script in the background to avoid blocking the profile execution,
# but redirect all output to a log file for debugging.
/users/taz/run_experiment.sh 2>&1 | tee /local/experiment_full_output.log

# Ensure the results directory and archive are readable by CloudLab's
# file transfer mechanism.
chmod -R 777 /local/results || true
chmod 644 /local/results.tar.gz || true
"""))
        # Add the source_fs service to the HDSearch node to pull back results
        node.addService(emulab.SourceFs(params.source_fs))

    else: # For additional generic nodes, if nodeCount > 1
        name = "node" + str(i)
        if params.useVMs: # Use the user's choice for other nodes
            node = request.XenVM(name)
        else:
            node = request.RawPC(name)
            pass
        if params.osImage and params.osImage != "default":
            node.disk_image = params.osImage
            pass
        # Add to lan
        if params.nodeCount > 1:
            iface = node.addInterface("eth1")
            lan.addInterface(iface)
            pass
        # Optional hardware type.
        if params.phystype != "":
            node.hardware_type = params.phystype
            pass
        # Optional Blockstore (user-defined)
        if params.tempFileSystemSize > 0 or params.tempFileSystemMax:
            bs = node.Blockstore(name + "-bs", params.tempFileSystemMount)
            if params.tempFileSystemMax:
                bs.size = "0GB"
            else:
                bs.size = str(params.tempFileSystemSize) + "GB"
                pass
            bs.placement = "any"
            pass
        pass

    # Add the VNC service to all nodes if requested
    if params.startVNC:
        node.startVNC()
        pass

# Print the RSpec to the enclosing page.
pc.printRequestRSpec(request)

```