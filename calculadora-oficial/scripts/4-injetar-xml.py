import xml.etree.ElementTree as ET
import re
import os

script_dir = os.path.dirname(os.path.abspath(__file__))
base_dir = os.path.dirname(script_dir)
input_dir = os.path.join(base_dir, 'input')
output_dir = os.path.join(base_dir, 'output')

def inject_xml_content(source_file, target_file, output_file):
    """
    Injeta o conteúdo RTC no XML da NFe em posições específicas usando regex
    """
    
    # Namespace da NFe
    NS = 'http://www.portalfiscal.inf.br/nfe'
    
    # Lê os arquivos
    with open(source_file, 'r', encoding='utf-8') as f:
        source_content = f.read()
    
    with open(target_file, 'r', encoding='utf-8') as f:
        target_content = f.read()
    
    # Detecta indentação do XML de destino
    # Procura por <imposto> para calcular indentação
    imposto_match = re.search(r'^(\s*)<imposto>', target_content, re.MULTILINE)
    total_match = re.search(r'^(\s*)<total>', target_content, re.MULTILINE)
    
    if not imposto_match or not total_match:
        print("ERRO: Nao foi possivel detectar indentacao")
        return False
    
    imposto_indent = len(imposto_match.group(1))
    total_indent = len(total_match.group(1))
    
    # Parse do XML fonte para extrair elementos
    source_root = ET.fromstring(source_content)
    
    # Extrai elementos do XML fonte (com namespace)
    source_det_imposto = source_root.find(f'.//{{{NS}}}det[@nItem="1"]/{{{NS}}}imposto')
    source_total = source_root.find(f'.//{{{NS}}}total')
    
    if not source_det_imposto or not source_total:
        print("ERRO: Elementos fonte nao encontrados")
        return False
    
    # Extrai IS e IBSCBS
    is_element = source_det_imposto.find(f'{{{NS}}}IS')
    ibscbs_element = source_det_imposto.find(f'{{{NS}}}IBSCBS')
    
    # Extrai ISTot e IBSCBSTot
    istot_element = source_total.find(f'{{{NS}}}ISTot')
    ibscbstot_element = source_total.find(f'{{{NS}}}IBSCBSTot')
    
    # Converte elementos para string XML (sem namespace prefix, apenas tags limpas)
    def element_to_xml_string(element, indent_spaces=10):
        """Converte elemento XML para string preservando estrutura"""
        if element is None:
            return ""
        
        xml_str = ET.tostring(element, encoding='unicode')
        
        # Remove declarações de namespace e prefixos
        xml_str = xml_str.replace(f' xmlns="{NS}"', '')
        xml_str = re.sub(r'<ns\d+:', '<', xml_str)
        xml_str = re.sub(r'</ns\d+:', '</', xml_str)
        xml_str = re.sub(r' xmlns:ns\d+="[^"]*"', '', xml_str)
        
        # Formata linha por linha mantendo conteúdo junto com tags
        from xml.dom import minidom
        
        try:
            dom = minidom.parseString(xml_str)
            pretty = dom.toprettyxml(indent="  ")
            # Remove declaração XML e linhas vazias
            lines = [line for line in pretty.split('\n') if line.strip() and not line.strip().startswith('<?xml')]
            
            # Adiciona indentação base
            base_indent = ' ' * indent_spaces
            indented = [base_indent + line for line in lines]
            
            return '\n'.join(indented)
        except:
            # Fallback: retorna como está com indentação básica
            lines = xml_str.split('\n')
            base_indent = ' ' * indent_spaces
            return '\n'.join([base_indent + line for line in lines if line.strip()])
    
    # Converte elementos para strings (usa indentação detectada + 2 para elementos filhos)
    is_xml = element_to_xml_string(is_element, indent_spaces=imposto_indent + 2)
    ibscbs_xml = element_to_xml_string(ibscbs_element, indent_spaces=imposto_indent + 2)
    istot_xml = element_to_xml_string(istot_element, indent_spaces=total_indent + 2)
    ibscbstot_xml = element_to_xml_string(ibscbstot_element, indent_spaces=total_indent + 2)
    
    # 1. Injeta IS e IBSCBS ao final de <imposto>, antes de </imposto>
    imposto_pattern = r'(\s*)(</imposto>)'
    
    if is_xml or ibscbs_xml:
        blocks_to_inject = []
        if is_xml:
            blocks_to_inject.append(is_xml)
            print("Bloco IS adicionado ao imposto")
        if ibscbs_xml:
            blocks_to_inject.append(ibscbs_xml)
            print("Bloco IBSCBS adicionado ao imposto")
        
        replacement = '\n' + '\n'.join(blocks_to_inject) + r'\1\2'
        target_content = re.sub(imposto_pattern, replacement, target_content, count=1)
    
    # 2. Injeta ISTot e IBSCBSTot ao final de <total>, antes de vNFTot (se existir) ou </total>
    # Primeiro tenta antes de vNFTot
    total_pattern = r'(\s*)(<vNFTot>)'
    total_match = re.search(total_pattern, target_content)
    
    if not total_match:
        # Se não tem vNFTot, injeta antes de </total>
        total_pattern = r'(\s*)(</total>)'
    
    if istot_xml or ibscbstot_xml:
        blocks_to_inject = []
        if istot_xml:
            blocks_to_inject.append(istot_xml)
            print("Bloco ISTot adicionado ao total")
        if ibscbstot_xml:
            blocks_to_inject.append(ibscbstot_xml)
            print("Bloco IBSCBSTot adicionado ao total")
        
        replacement = '\n' + '\n'.join(blocks_to_inject) + r'\1\2'
        target_content = re.sub(total_pattern, replacement, target_content, count=1)
    
    # Salva o arquivo
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(target_content)
    
    return True

# Executa injeção
success = inject_xml_content(
    os.path.join(output_dir, 'saida-gerar-xml.xml'),
    os.path.join(input_dir, 'nfe-sem-rtc.xml'),
    os.path.join(output_dir, 'nfe-com-rtc.xml')
)

if success:
    print("\nXML da RTC injetado na NFe com sucesso!")
else:
    print("\nFalha ao injetar XML da RTC")
    exit(1)