@echo off
setlocal
cd /d "%~dp0"

echo ========================================
echo   Compilando Desemprego Bot
 echo ========================================

if not exist "desemprego_bot_melhorado.py" (
    echo ERRO: coloque este .bat na mesma pasta do arquivo desemprego_bot_melhorado.py
    pause
    exit /b 1
)

if not exist "audios" (
    echo ERRO: a pasta audios nao foi encontrada.
    pause
    exit /b 1
)

if not exist "programa_image" (
    echo ERRO: a pasta programa_image nao foi encontrada.
    pause
    exit /b 1
)

echo Limpando compilacao anterior...
if exist "build" rmdir /s /q "build"
if exist "dist" rmdir /s /q "dist"
if exist "Desemprego Bot.spec" del /q "Desemprego Bot.spec"

python -m PyInstaller --noconfirm --clean --noconsole --onedir ^
  --name "Desemprego Bot" ^
  --icon "programa_image\icon.ico" ^
  --collect-all pygame ^
  --add-data "audios;audios" ^
  --add-data "programa_image;programa_image" ^
  --add-data "imagem.png;." ^
  "desemprego_bot_melhorado.py"

if errorlevel 1 (
    echo.
    echo ERRO: a compilacao falhou.
    echo Para ver a mensagem completa, troque --noconsole por --console neste arquivo e tente novamente.
    pause
    exit /b 1
)

echo.
echo ========================================
echo Compilacao concluida!
echo O programa esta em:
echo dist\Desemprego Bot\Desemprego Bot.exe
echo ========================================
pause
