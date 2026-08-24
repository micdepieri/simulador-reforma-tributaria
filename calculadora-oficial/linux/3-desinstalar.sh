#!/bin/bash

# Remove calculadora containers
echo "Removendo containers da calculadora..."
docker rm -vf $(docker ps -aq --filter "name=calculadora") 2>/dev/null || echo "Nenhum container da calculadora encontrado."

# Remove calculadora images
echo "Removendo imagens da calculadora..."
docker rmi -f $(docker images -q --filter "reference=calculadora*") 2>/dev/null || echo "Nenhuma imagem da calculadora encontrada."

echo "Limpeza da calculadora concluída!"