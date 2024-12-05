#!/bin/bash

echo "Starting Docker build process..."
docker build -t ctf05/runpodhunyuanvideo:latest .

echo "Docker build completed. Starting push to registry..."
docker push ctf05/runpodhunyuanvideo:latest

echo "Process completed successfully!"
echo
echo "Press any key to exit..."
read -n 1 -s -r