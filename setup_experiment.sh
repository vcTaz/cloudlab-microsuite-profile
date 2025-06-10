#!/bin/bash

# Ensure this script is run as root or with sudo
if [ "$EUID" -ne 0 ]; then
  echo "Error: This script must be run as root or with sudo."
  exit 1
fi

echo "Starting CloudLab MicroSuite experiment setup..."

# --- Disk Partitioning and Mounting ---
echo "1. Partitioning and mounting /dev/sda4..."
# mkfs.ext4 /dev/sda4 will format the disk
mkfs.ext4 /dev/sda4 || { echo "Error: Failed to format /dev/sda4"; exit 1; }

# mkextrafs.pl typically handles formatting and mounting the ephemeral disk
# if you specify a tempFileSystemMount in the profile.
# It usually mounts to /mydata. If /dev/sda4 is separate and intended for /mnt/newdata
# as a secondary large disk, then the commands below are fine.
# If /dev/sda4 is the same disk as what CloudLab makes /mydata, these commands might cause issues.
# Assuming /dev/sda4 is a separate, unformatted disk provided by your hardware type.
/usr/local/etc/emulab/mkextrafs.pl /mydata # This typically sets up the primary ephemeral disk, which might be sda3 or similar.
                                         # Keep this if /mydata is separate from /mnt/newdata on sda4.

mkdir -p /mnt/newdata || { echo "Error: Failed to create /mnt/newdata"; exit 1; }
mount /dev/sda4 /mnt/newdata || { echo "Error: Failed to mount /dev/sda4 to /mnt/newdata"; exit 1; }
echo "/dev/sda4 /mnt/newdata ext4 defaults 0 0" | tee -a /etc/fstab || { echo "Error: Failed to update /etc/fstab"; exit 1; }
echo "Disk setup complete. Current disk usage:"
df -h | grep /mnt/newdata

echo "2. Setting permissions for /mnt/newdata..."
cd /mnt/newdata/ || { echo "Error: Failed to change directory to /mnt/newdata"; exit 1; }
chmod -R g+w . || { echo "Error: Failed to set group write permissions"; exit 1; }
chmod -R 777 . || { echo "Warning: Setting 777 permissions. Consider stricter permissions for production environments."; }
echo "Permissions set."

# --- MicroSuite Clone and Setup ---
echo "3. Cloning/updating MicroSuite repository..."
# Go to /mnt/newdata to clone MicroSuite there
cd /mnt/newdata/ || { echo "Error: Failed to change directory to /mnt/newdata before cloning."; exit 1; }

if [ ! -d "MicroSuite" ]; then
  git clone https://github.com/vcTaz/MicroSuite.git || { echo "Error: Failed to clone MicroSuite repo"; exit 1; }
  cd MicroSuite || { echo "Error: Failed to enter MicroSuite directory after clone"; exit 1; }
else
  echo "MicroSuite directory already exists. Pulling latest changes..."
  cd MicroSuite || { echo "Error: Failed to enter MicroSuite directory"; exit 1; }
  git pull || { echo "Warning: Failed to pull latest MicroSuite changes. Proceeding anyway."; }
fi

echo "4. Running MicroSuite setup script..."
sh setup_node_mydata.sh || { echo "Error: MicroSuite setup_node_mydata.sh failed"; exit 1; }
echo "MicroSuite setup script finished."

# --- Docker Compose Deployment ---
echo "5. Starting Docker Compose services..."
# Ensure docker-compose is installed and available in PATH
# (setup_node_mydata.sh should handle Docker/Docker Compose installation)
docker compose up -d || { echo "Error: Docker Compose failed to start. Check Docker installation."; exit 1; }
echo "Docker services started."
echo "Running Docker containers:"
docker ps

# --- Git Configuration and Merge ---
echo "6. Configuring Git and merging from fork..."
git remote add fork https://github.com/svassi04/MicroSuite.git || true # Add || true to avoid error if remote exists
git fetch fork || { echo "Error: Failed to fetch from fork"; exit 1; }

# Use the environment variables passed from the CloudLab profile
if [ -z "$GIT_USERNAME" ] || [ -z "$GIT_USEREMAIL" ]; then
  echo "Warning: GIT_USERNAME or GIT_USEREMAIL not set. Skipping global git config."
else
  git config --global user.name "$GIT_USERNAME"
  git config --global user.email "$GIT_USEREMAIL"
  echo "Git global user configured."
fi

git stash save "Stash before merging from fork" || true # Use || true to avoid error if nothing to stash
git merge fork/master || { echo "Error: Failed to merge from fork/master"; exit 1; }
echo "Git operations complete."

echo "CloudLab experiment setup finished successfully!"

echo "Script finished successfully !" > /tmp/status.txt
