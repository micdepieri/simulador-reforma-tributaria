import requests
import os

# Determina caminhos relativos ao script
script_dir = os.path.dirname(os.path.abspath(__file__))
base_dir = os.path.dirname(script_dir)
output_dir = os.path.join(base_dir, 'output')

url = "http://localhost:8080/api/calculadora/xml/validate"

# Carrega XML gerado anteriormente
input_file = os.path.join(output_dir, 'saida-gerar-xml.xml')
with open(input_file, 'r', encoding='utf-8') as file:
    xml_content = file.read()

# Define tipo e subtipo do documento
params = {
    'tipo': 'nfe',
    'subtipo': 'grupo'
}

try:
    response = requests.post(
        url, 
        data=xml_content, 
        params=params,
        headers={'Content-Type': 'application/xml'}
    )
    
    if response.status_code == 200:
        print("XML valido!")
        print(f"Resposta: {response.text}")
    else:
        print(f"XML invalido: {response.status_code}")
        print(f"Erros: {response.text}")
        exit(1)
        
except requests.exceptions.RequestException as e:
    print(f"Erro de conexao: {e}")
    exit(1)
