#!/bin/bash
# Script para testar o sistema de rastreamento - Modo Competição
# Exemplo de uso:
#   bash runin.sh [flip_camera] [horizontal|vertical]
# Exemplos:
#   bash runin.sh
#   bash runin.sh flip_camera
#   bash runin.sh vertical
#   bash runin.sh flip_camera horizontal

# Cores para output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

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
# Verificar argumentos para flip_camera
FLIP_CAMERA=""
for arg in "$@"; do
    if [ "$arg" = "flip_camera" ]; then
        FLIP_CAMERA="--flip_camera"
        break
    fi
done
# Verificar argumentos para trigger_orientation
TRIGGER_ORIENTATION="horizontal"  # valor padrão
for arg in "$@"; do
if [[ "$arg" == "horizontal" || "$arg" == "vertical" ]]; then
    TRIGGER_ORIENTATION="$arg"
    break
fi
done
# Verificar modelos disponíveis
MODELS_AVAILABLE=()
if [ -f "model-v8.pt" ]; then
    MODELS_AVAILABLE+=("model-v8.pt")
fi
if [ -f "model-v9.pt" ]; then
    MODELS_AVAILABLE+=("model-v9.pt")
fi
if [ -f "model-v14.pt" ]; then
    MODELS_AVAILABLE+=("model-v14.pt")
fi
if [ -f "best.pt" ]; then
    MODELS_AVAILABLE+=("best.pt")
fi
if [ -f "model-v16.pt" ]; then
    MODELS_AVAILABLE+=("model-v16.pt")
fi

# Selecionar modelo
echo "Modelos disponíveis:"
for i in "${!MODELS_AVAILABLE[@]}"; do
    echo "$((i+1))) ${MODELS_AVAILABLE[$i]}"
done
echo ""
read -p "Escolha o modelo (1-${#MODELS_AVAILABLE[@]}): " MODEL_CHOICE

# Validar escolha
if [ -z "$MODEL_CHOICE" ] || [ "$MODEL_CHOICE" -lt 1 ] || [ "$MODEL_CHOICE" -gt ${#MODELS_AVAILABLE[@]} ]; then
    echo -e "${RED}❌ Escolha inválida! Usando primeiro modelo disponível.${NC}"
    MODEL="${MODELS_AVAILABLE[0]}"
else
    MODEL="${MODELS_AVAILABLE[$((MODEL_CHOICE-1))]}"
fi

echo -e "${GREEN}✓ Usando modelo: $MODEL${NC}"
echo ""

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
    --api_url "https://achecourtroom-backend.onrender.com/analise/add"