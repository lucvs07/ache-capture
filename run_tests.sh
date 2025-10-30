#!/bin/bash
# Script para testar o sistema de rastreamento com diferentes configurações

echo "=================================="
echo "🎯 Sistema de Rastreamento - Testes"
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

echo "✓ Usando: python3"
echo ""

# Cores para output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

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

# Verificar se há modelos disponíveis
if [ ${#MODELS_AVAILABLE[@]} -eq 0 ]; then
    echo -e "${RED}❌ Nenhum modelo encontrado!${NC}"
    echo "Por favor, certifique-se de ter um dos seguintes modelos:"
    echo "  - model-v8.pt"
    echo "  - model-v9.pt"
    echo "  - model-v14.pt"
    echo "  - tracelifemvp/my_model.pt"
    echo "  - model-v9.pt"
    echo "  - tracelifemvp/my_model.pt"
    exit 1
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

# Menu de opções
echo "Escolha o tipo de teste:"
echo "1) Webcam (USB0) - Teste básico"
echo "2) Webcam (USB0) - Com salvamento local"
echo "3) Vídeo - Teste básico"
echo "4) Vídeo - Com salvamento local"
echo "5) Vídeo - Com API local"
echo "6) Vídeo - Completo (API + Salvamento)"
echo "7) Personalizado"
echo ""
read -p "Opção (1-7): " OPTION

case $OPTION in
    1)
        echo -e "${YELLOW}🚀 Iniciando teste com webcam...${NC}"
        python3 yolo_detect.py \
            --model "$MODEL" \
            --source usb0 \
            --thresh 0.5 \
            --trigger_line 50 \
            --resolution 1280x720
        ;;
    
    2)
        echo -e "${YELLOW}🚀 Iniciando teste com webcam + salvamento local...${NC}"
        mkdir -p capturas_webcam
        python3 yolo_detect.py \
            --model "$MODEL" \
            --source usb0 \
            --thresh 0.5 \
            --trigger_line 50 \
            --resolution 1280x720 \
            --save_crossings \
            --output_dir capturas_webcam
        ;;
    
    3)
        read -p "Caminho do vídeo: " VIDEO_PATH
        if [ ! -f "$VIDEO_PATH" ]; then
            echo -e "${RED}❌ Vídeo não encontrado: $VIDEO_PATH${NC}"
            exit 1
        fi
        echo -e "${YELLOW}🚀 Iniciando teste com vídeo...${NC}"
        python3 yolo_detect.py \
            --model "$MODEL" \
            --source "$VIDEO_PATH" \
            --thresh 0.5 \
            --trigger_line 50
        ;;
    
    4)
        read -p "Caminho do vídeo: " VIDEO_PATH
        if [ ! -f "$VIDEO_PATH" ]; then
            echo -e "${RED}❌ Vídeo não encontrado: $VIDEO_PATH${NC}"
            exit 1
        fi
        echo -e "${YELLOW}🚀 Iniciando teste com vídeo + salvamento local...${NC}"
        mkdir -p resultados_video
        python3 yolo_detect.py \
            --model "$MODEL" \
            --source "$VIDEO_PATH" \
            --thresh 0.5 \
            --trigger_line 50 \
            --save_crossings \
            --output_dir resultados_video
        echo ""
        echo -e "${GREEN}✓ Imagens salvas em: resultados_video/${NC}"
        ;;
    
    5)
        read -p "Caminho do vídeo: " VIDEO_PATH
        if [ ! -f "$VIDEO_PATH" ]; then
            echo -e "${RED}❌ Vídeo não encontrado: $VIDEO_PATH${NC}"
            exit 1
        fi
        read -p "URL da API (padrão: http://localhost:3000/api/products): " API_URL
        API_URL=${API_URL:-http://localhost:3000/api/products}
        
        echo -e "${YELLOW}🚀 Iniciando teste com vídeo + API...${NC}"
        mkdir -p resultados_api
        python3 yolo_detect.py \
            --model "$MODEL" \
            --source "$VIDEO_PATH" \
            --thresh 0.5 \
            --trigger_line 50 \
            --save_crossings \
            --output_dir resultados_api \
            --api_url "$API_URL"
        ;;
    
    6)
        read -p "Caminho do vídeo: " VIDEO_PATH
        if [ ! -f "$VIDEO_PATH" ]; then
            echo -e "${RED}❌ Vídeo não encontrado: $VIDEO_PATH${NC}"
            exit 1
        fi
        read -p "URL da API (padrão: http://localhost:3000/api/products): " API_URL
        API_URL=${API_URL:-http://localhost:3000/api/products}
        read -p "Posição da trigger line 0-100 (padrão: 50): " TRIGGER
        TRIGGER=${TRIGGER:-50}
        
        echo -e "${YELLOW}🚀 Iniciando teste completo...${NC}"
        mkdir -p resultados_completo
        python3 yolo_detect.py \
            --model "$MODEL" \
            --source "$VIDEO_PATH" \
            --thresh 0.5 \
            --trigger_line "$TRIGGER" \
            --save_crossings \
            --output_dir resultados_completo \
            --api_url "$API_URL"
        ;;
    
    7)
        echo "Modo personalizado - Configure os parâmetros:"
        read -p "Fonte (usb0, video.mp4, etc): " SOURCE
        read -p "Threshold (padrão: 0.5): " THRESH
        THRESH=${THRESH:-0.5}
        read -p "Trigger line 0-100 (padrão: 50): " TRIGGER
        TRIGGER=${TRIGGER:-50}
        read -p "Salvar cruzamentos? (s/n): " SAVE
        
        CMD="python3 yolo_detect.py --model $MODEL --source $SOURCE --thresh $THRESH --trigger_line $TRIGGER"
        
        if [[ $SAVE == "s" || $SAVE == "S" ]]; then
            read -p "Pasta de saída (padrão: crossings): " OUTPUT
            OUTPUT=${OUTPUT:-crossings}
            mkdir -p "$OUTPUT"
            CMD="$CMD --save_crossings --output_dir $OUTPUT"
        fi
        
        read -p "URL da API (deixe em branco para pular): " API_URL
        if [ ! -z "$API_URL" ]; then
            CMD="$CMD --api_url $API_URL"
        fi
        
        read -p "Resolução (ex: 1280x720, deixe em branco para auto): " RES
        if [ ! -z "$RES" ]; then
            CMD="$CMD --resolution $RES"
        fi
        
        echo ""
        echo -e "${YELLOW}Executando: $CMD${NC}"
        eval $CMD
        ;;
    
    *)
        echo -e "${RED}❌ Opção inválida!${NC}"
        exit 1
        ;;
esac

echo ""
echo -e "${GREEN}✓ Teste finalizado!${NC}"
