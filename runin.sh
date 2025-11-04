#!/bin/bash
# Script para testar o sistema de rastreamento - Modo Competição

echo "=================================="
echo "🎯 Sistema de Rastreamento - Modo Competição"
echo "=================================="
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

# Perguntar se quer rodar o modo competição
echo "Confirmar Execução:"
echo "1) Sim"
echo "2) Não"
echo ""
read -p "Escolha (1-2, padrão: 1): " CONFIRM_CHOICE
CONFIRM_CHOICE=${CONFIRM_CHOICE:-1}
if [ "$CONFIRM_CHOICE" -ne 1 ]; then
    echo "Execução cancelada pelo usuário."
    exit 0
fi
echo -e "🚀 Iniciando..."
        python3 yolo_detect.py \
            --model "$MODEL" \
            --source usb0 \
            --thresh 0.3 \
            --trigger_line 65 \
            --trigger_orientation "$TRIGGER_ORIENTATION" \
            $FLIP_CAMERA \
            --resolution 1280x720 \
            --api_url "$API_URL=https://achecourtroom-backend.onrender.com/analise/add" \
        ;;