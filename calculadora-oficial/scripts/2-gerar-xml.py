import requests
import json
import os

# Determina caminhos relativos ao script
script_dir = os.path.dirname(os.path.abspath(__file__))
base_dir = os.path.dirname(script_dir)
output_dir = os.path.join(base_dir, 'output')

url = "http://localhost:8080/api/calculadora/xml/generate"

# Carrega resultado do cálculo anterior
input_file = os.path.join(output_dir, 'saida-regime-geral.json')
with open(input_file, 'r', encoding='utf-8') as file:
    json_data = json.load(file)

# Define o tipo de documento (NFe por padrão)
params = {
    'tipo': 'NFe'
}

try:
    # Gera XML a partir do cálculo
    response = requests.post(
        url, 
        json=json_data, 
        params=params,
        headers={
            'Content-Type': 'application/json',
            'Accept': 'application/xml'
        }
    )
    
    if response.status_code == 200:
        # Salva XML gerado
        output_file = os.path.join(output_dir, 'saida-gerar-xml.xml')
        with open(output_file, 'w', encoding='utf-8') as file:
            file.write(response.text)
        print("XML gerado com sucesso!")
        print(f"Arquivo gerado: {output_file}")
    else:
        print(f"Erro na requisicao: {response.status_code}")
        print(f"Resposta: {response.text}")
        exit(1)
        
except requests.exceptions.RequestException as e:
    print(f"Erro de conexao: {e}")
    exit(1)
