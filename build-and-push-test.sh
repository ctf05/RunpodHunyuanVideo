#!/bin/bash

echo "Pulling repo"
git pull

echo "Starting Docker build process..."
docker build -t 192.168.86.119:5000/ctf05/runpodhunyuanvideo:latest .

echo "Docker build completed. Starting push to registry..."
docker push 192.168.86.119:5000/ctf05/runpodhunyuanvideo:latest

echo "Process completed successfully!"
echo
echo "Press any key to exit..."
read -n 1 -s -r