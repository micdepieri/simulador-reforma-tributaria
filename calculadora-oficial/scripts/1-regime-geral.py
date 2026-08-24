import requests
import json
import os

# Determina caminhos relativos ao script
script_dir = os.path.dirname(os.path.abspath(__file__))
base_dir = os.path.dirname(script_dir)
input_dir = os.path.join(base_dir, 'input')
output_dir = os.path.join(base_dir, 'output')

url = "http://localhost:8080/api/calculadora/regime-geral"

# Carrega dados de entrada
input_file = os.path.join(input_dir, 'entrada-regime-geral.json')
with open(input_file, 'r', encoding='utf-8') as file:
    body = json.load(file)

# Chama API da calculadora
response = requests.post(url, json=body, headers={'Content-Type': 'application/json'})

if response.status_code == 200:
    # Salva resultado do cálculo
    output_file = os.path.join(output_dir, 'saida-regime-geral.json')
    with open(output_file, 'w', encoding='utf-8') as file:
        json.dump(response.json(), file, indent=2, ensure_ascii=False)
    
    print("Calculo de tributos realizado com sucesso!")
    print(f"Status: {response.status_code}")
    print(f"Arquivo gerado: {output_file}")
else:
    print(f"Erro na requisicao: {response.status_code}")
    print(f"Resposta: {response.text}")
    exit(1)
