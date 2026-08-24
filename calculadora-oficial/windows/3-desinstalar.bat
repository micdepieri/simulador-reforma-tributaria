@echo off
echo Desinstalando a Calculadora no WSL...
echo.

wsl --shuwdown >nul 2>&1
wsl --unregister calculadora 
cd ..
rmdir /s calculadora 

echo.
echo Desinstalacao concluida!
echo.
echo Pressione qualquer tecla para continuar...
pause