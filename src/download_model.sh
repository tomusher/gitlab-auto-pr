#!/bin/bash

MODEL_DIR="models"
MODEL_FILE="$MODEL_DIR/jina-embeddings-v2-small-en-q5_k_m.gguf"
MODEL_URL="https://huggingface.co/djuna/jina-embeddings-v2-small-en-Q5_K_M-GGUF/resolve/main/jina-embeddings-v2-small-en-q5_k_m.gguf"

# Create models directory if it doesn't exist
mkdir -p $MODEL_DIR

# Download model if it doesn't exist
if [ ! -f "$MODEL_FILE" ]; then
    echo "Downloading embedding model..."
    curl -L $MODEL_URL -o $MODEL_FILE
    echo "Model downloaded successfully!"
else
    echo "Model already exists, skipping download."
fi