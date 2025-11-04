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