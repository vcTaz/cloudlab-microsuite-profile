#!/bin/bash

# Format and mount the extra disk
mkfs.ext4 /dev/sda4
/usr/local/etc/emulab/mkextrafs.pl /mydata
mkdir -p /mnt/newdata
mount /dev/sda4 /mnt/newdata
echo "/dev/sda4 /mnt/newdata ext4 defaults 0 0" >> /etc/fstab
chmod -R 777 /mnt/newdata

# Install Docker and dependencies
apt update
apt install -y docker.io git curl unzip

systemctl enable docker
systemctl start docker

# Clone MicroSuite
cd /mnt/newdata
git clone https://github.com/svassi04/MicroSuite.git
cd MicroSuite
chmod +x setup_node_mydata.sh
./setup_node_mydata.sh

# Run Docker Compose
docker compose up -d

