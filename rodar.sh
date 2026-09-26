#!/usr/bin/env sh
# NFL GAMES - inicia o app no Linux e no macOS:  ./rodar.sh
# A logica fica no rodar.py, o mesmo do Windows (python rodar.py) e do executavel.
# Opcoes: ./rodar.sh --port 9000 | --offline | --sem-navegador
cd "$(dirname "$0")" || exit 1

if command -v python3 >/dev/null 2>&1; then
    exec python3 rodar.py "$@"
elif command -v python >/dev/null 2>&1; then
    exec python rodar.py "$@"
fi

echo "[ERRO] Python nao encontrado. Instale o Python 3.10 ou mais novo (ex.: sudo apt install python3 python3-pip)." >&2
exit 1
