#!/bin/bash
# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.
#
# Install all required tools for image definitions
#
set -e

sudo apt update
sudo apt install -y make
sudo apt install -y runc containerd
sudo apt install -y docker.io
sudo apt install -y zip
sudo snap install jq
sudo snap install go --classic
sudo snap install trivy
sudo snap install docker
sudo groupadd -f docker
sudo usermod -aG docker $USER
mkdir -p /home/$USER/.docker
sudo chown "$USER":"$USER" /home/"$USER"/.docker -R
sudo chmod g+rwx "$HOME/.docker" -R
echo "Installed docker, created docker group and added user '$USER' to docker group"
echo "Either logout/login or run 'newgrp docker' to be able to connect to Docker daemon"

