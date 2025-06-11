#!/bin/bash

# Ensure script is run with sudo
if [[ $EUID -ne 0 ]]; then
   echo "Please run this script with sudo:"
   echo "  sudo $0"
   exit 1
fi

echo "==> Formatting /dev/sda4"
mkfs.ext4 /dev/sda4

echo "==> Creating extra filesystem with emulab"
 /usr/local/etc/emulab/mkextrafs.pl /mydata

echo "==> Checking disk UUID"
blkid /dev/sda4

echo "==> Mounting new storage"
mkdir -p /mnt/newdata
mount /dev/sda4 /mnt/newdata

echo "==> Persisting mount in /etc/fstab"
echo "/dev/sda4 /mnt/newdata ext4 defaults 0 0" >> /etc/fstab
df -h | grep /mnt/newdata

echo "==> Setting full permissions on /mnt/newdata"
chmod -R 777 /mnt/newdata

echo "==> Cloning MicroSuite repository"
cd /mnt/newdata
git clone https://github.com/svassi04/MicroSuite.git
cd MicroSuite

echo "==> Running MicroSuite setup"
sh setup_node_mydata.sh

echo "==> Starting MicroSuite Docker containers"
docker compose up -d

echo "==> Waiting a few seconds for containers to start..."
sleep 10

# Find the container ID of the MicroSuite service
CONTAINER_ID=$(docker ps --filter "name=microsuite" --format "{{.ID}}" | head -n 1)

if [ -z "$CONTAINER_ID" ]; then
    echo "❌ Could not find a running MicroSuite container."
    docker ps
    exit 1
fi

echo "==> Entering container $CONTAINER_ID to pull latest code from fork"

# Run Git commands inside container
docker exec -it "$CONTAINER_ID" bash -c "
    cd MicroSuite && \
    git remote add fork https://github.com/vcTaz/MicroSuite.git && \
    git fetch fork && \
    git config --global user.name 'vcTaz' && \
    git config --global user.email 'tsazeides@gmail.com' && \
    git stash save 'Stash before merging from fork' && \
    git merge fork/master
"

echo "✅ Setup complete."
