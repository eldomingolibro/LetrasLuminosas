#!/bin/bash
# Arranca Letras Luminosas en local -> http://127.0.0.1:5001
cd "$(dirname "$0")"

# crea el entorno virtual la primera vez
if [ ! -d venv ]; then
  echo "Creando entorno virtual (solo la primera vez)..."
  python3 -m venv venv
  ./venv/bin/pip install --upgrade pip
  ./venv/bin/pip install -r requirements.txt
fi

echo "Abriendo http://127.0.0.1:5001 ..."
( sleep 2; open "http://127.0.0.1:5001" ) &
./venv/bin/python app.py
