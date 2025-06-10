#!/bin/bash

# Ensure the script exits if any command fails
set -e

echo "Starting experiment setup script..."

# Disk formatting and mounting
sudo mkfs.ext4 /dev/sda4
sudo /usr/local/etc/emulab/mkextrafs.pl /mydata
sudo blkid /dev/sda4

sudo mkdir -p /mnt/newdata
sudo mount /dev/sda4 /mnt/newdata
echo "/dev/sda4 /mnt/newdata ext4 defaults 0 0" | sudo tee -a /etc/fstab
df -h | grep /mnt/newdata
cd /mnt/newdata/
sudo chmod -R g+w ./

# Be cautious with 777 permissions in production, but for experiments, it's common
sudo chmod -R 777 /mnt/newdata/
cd /mnt/newdata/

# Clone your MicroSuite repository
git clone https://github.com/svassi04/MicroSuite.git
cd MicroSuite

# Run MicroSuite's setup script
sudo sh setup_node_mydata.sh

# Start Docker Compose services
sudo docker compose up -d

# Docker commands that need manual interaction after setup
echo "Docker services are up. To interact with a container:"
echo "1. Run: sudo docker ps"
echo "2. Find the CONTAINER ID of your desired service."
echo "3. Execute: sudo docker exec -it <CONTAINER_ID> bash"

# Git configuration and merging (using passed arguments for username/email)
# You'll need to pass these as arguments to the script from the RSpec
GIT_USERNAME="$1"
GIT_USEREMAIL="$2"

cd MicroSuite
git remote add fork https://github.com/vcTaz/MicroSuite.git
git fetch fork
git config --global user.name "${GIT_USERNAME}"
git config --global user.email "${GIT_USEREMAIL}"
git stash save "Stash before merging from fork"
git merge fork/master

echo "Experiment setup script completed."
echo "done" > /tmp/status.txt
