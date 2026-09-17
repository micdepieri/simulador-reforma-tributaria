# -*- coding: utf-8 -*-
"""Converte o relatório HTML em PDF usando o navegador já instalado.

Sem dependência nova: usa Chrome ou Edge em modo headless, que praticamente
toda máquina Windows já tem. Se nenhum for encontrado, não é erro — o HTML
continua lá e o usuário imprime com Ctrl+P > Salvar como PDF, que produz o
mesmo resultado (o CSS de impressão já está no documento).

Uso direto:
    python3 motor/exportar_pdf.py saidas/<empresa>/relatorio_base.html
"""
import os
import subprocess
import sys

# Caminhos usuais no Windows; o primeiro que existir é usado.
NAVEGADORES = (
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/usr/bin/google-chrome",
    "/usr/bin/chromium",
)


def encontrar_navegador():
    for caminho in NAVEGADORES:
        if os.path.exists(caminho):
            return caminho
    return None


def exportar(html_path, pdf_path=None, timeout=120):
    """Gera o PDF ao lado do HTML. Devolve o caminho, ou None se não deu.

    Nunca levanta exceção: exportar PDF é conveniência, não pode derrubar
    uma simulação que já terminou.
    """
    navegador = encontrar_navegador()
    if not navegador:
        return None
    html_path = os.path.abspath(html_path)
    if pdf_path is None:
        pdf_path = os.path.splitext(html_path)[0] + ".pdf"
    # file:// com caminho absoluto; o Chrome cuida de espaços e acentos
    url = "file:///" + html_path.replace("\\", "/").lstrip("/")
    comando = [
        navegador, "--headless", "--disable-gpu",
        "--no-pdf-header-footer",          # a numeração já está no documento
        "--print-to-pdf=%s" % pdf_path,
        url,
    ]
    try:
        subprocess.run(comando, capture_output=True, timeout=timeout, check=False)
    except (OSError, subprocess.SubprocessError):
        return None
    return pdf_path if os.path.exists(pdf_path) else None


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    destino = exportar(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else None)
    if destino:
        print("PDF gerado: %s" % destino)
    else:
        print("Nenhum navegador compatível encontrado (Chrome/Edge). "
              "Abra o HTML e use Ctrl+P > Salvar como PDF.")
        sys.exit(1)


if __name__ == "__main__":
    main()
