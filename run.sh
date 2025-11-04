#!/bin/bash
# Script para executar o sistema de rastreamento em modo de competição.

echo "=============================================="
echo "🏆 Executando em Modo de Competição 🏆"
echo "=============================================="
echo ""

# Ativar ambiente virtual se existir
if [ -d "venv" ]; then
    source venv/bin/activate
    echo "✓ Ambiente virtual ativado"
fi

# Detectar comando Python correto
if command -v python3 &> /dev/null; then
    PYTHON_CMD="python3"
elif command -v python &> /dev/null; then
    PYTHON_CMD="python"
else
    echo "❌ Python não encontrado! Instale Python 3.8+ primeiro."
    exit 1
fi

echo "✓ Usando: $PYTHON_CMD"
echo ""

# --- Configurações de Competição ---
MODEL="model-v16.pt"
SOURCE="usb0"
API_URL="https://achecourtroom-backend.onrender.com/analise/add"
TRIGGER_ORIENTATION="horizontal"
TRIGGER_LINE=65
SAVE_DIR="resultados_competicao"
THRESH=0.5 # Usando um valor padrão, pode ser ajustado se necessário

# Criar diretório de saída
mkdir -p $SAVE_DIR

# Montar o comando
COMMAND="$PYTHON_CMD yolo_detect.py \\
    --model \"$MODEL\" \\
    --source \"$SOURCE\" \\
    --thresh $THRESH \\
    --trigger_line $TRIGGER_LINE \\
    --trigger_orientation \"$TRIGGER_ORIENTATION\" \\
    --save_crossings \\
    --output_dir \"$SAVE_DIR\" \\
    --api_url \"$API_URL\""

# --- Confirmação do Usuário ---
echo "O seguinte comando será executado:"
echo "------------------------------------------------"
echo "$COMMAND"
echo "------------------------------------------------"
echo ""

read -p "Pressione [Enter] para iniciar ou [Ctrl+C] para cancelar..."

# --- Execução ---
echo ""
echo "🚀 Iniciando a execução..."
eval $COMMAND

echo ""
echo "✅ Execução finalizada."
