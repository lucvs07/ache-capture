# 🎯 ACHE Capture - Sistema de Detecção e Rastreamento YOLO

Sistema completo de visão computacional para detecção, rastreamento e captura de objetos em tempo real usando YOLO, com trigger line vertical configurável e integração com APIs externas.

---

## 📋 Índice

1. [Visão Geral](#-visão-geral)
2. [Instalação](#-instalação)
3. [Como Usar](#-como-usar)
4. [Parâmetros e Configurações](#-parâmetros-e-configurações)
5. [Exemplos de Uso](#-exemplos-de-uso)
6. [Estrutura do Projeto](#-estrutura-do-projeto)
7. [Funcionalidades](#-funcionalidades)
8. [Correções e Melhorias](#-correções-e-melhorias)
9. [Troubleshooting](#-troubleshooting)
10. [Contribuições](#-contribuições)

---

## 🌟 Visão Geral

Este sistema permite:
- ✅ Detectar objetos usando modelos YOLO (v8, v9 ou customizados)
- ✅ Rastrear objetos em movimento com IDs únicos
- ✅ Detectar quando objetos cruzam uma linha vertical (trigger line)
- ✅ Capturar fotos automaticamente no momento do cruzamento
- ✅ Enviar análises para APIs externas
- ✅ Upload automático para Cloudinary (opcional)
- ✅ Salvar imagens localmente para análise
- ✅ Funcionar com vídeos, webcams ou streams

### Tecnologias Principais
- **Python 3.8+**
- **YOLOv8/v9** (Ultralytics)
- **OpenCV** (Processamento de vídeo)
- **BoT-SORT** (Rastreamento multi-objeto)
- **Cloudinary** (Upload de imagens - opcional)
- **NumPy & PyTorch** (Processamento numérico)

---

## 🚀 Instalação

### 1. Pré-requisitos

- macOS, Linux ou Windows
- Python 3.8 ou superior
- Git (opcional)

### 2. Criar e Ativar Ambiente Virtual

```bash
# Navegar até a pasta do projeto
cd /Users/velosofilho/Projetos/ache-capture-v1

# Criar ambiente virtual
python3 -m venv venv

# Ativar ambiente virtual
# macOS/Linux:
source venv/bin/activate

# Windows:
venv\Scripts\activate

# Você verá (venv) no início do prompt
```

### 3. Instalar Dependências

```bash
# Opção 1: Instalar todas de uma vez
pip install -r requirements.txt

# Opção 2: Instalar manualmente
pip install python-dotenv cloudinary opencv-python ultralytics requests numpy lap torch
```

### 4. Configurar Variáveis de Ambiente (Opcional)

Se for usar Cloudinary para upload de imagens:

```bash
# Criar arquivo .env
touch .env
```

Adicione as credenciais no arquivo `.env`:

```env
CLOUDINARY_CLOUD_NAME=seu_cloud_name
CLOUDINARY_API_KEY=sua_api_key
CLOUDINARY_API_SECRET=seu_api_secret
```

### 5. Verificar Instalação

```bash
# Verificar versão do Python
python3 --version  # Deve mostrar 3.8+

# Testar importações
python3 -c "import cv2; import ultralytics; print('✅ Tudo OK!')"
```

---

## ▶️ Como Usar

### Opção 1: Script Interativo (Recomendado)

```bash
# Ativar ambiente virtual
source venv/bin/activate

# Executar script interativo
./run_tests.sh
```

O script oferece um menu com as opções mais comuns.

### Opção 2: Comando Direto

```bash
# Ativar ambiente virtual
source venv/bin/activate

# Executar com vídeo
python3 yolo_detect.py \
  --model model-v8.pt \
  --source seu_video.mp4 \
  --thresh 0.5 \
  --trigger_line 50 \
  --save_crossings \
  --output_dir resultados
```

### Opção 3: Webcam ao Vivo

```bash
python3 yolo_detect.py \
  --model model-v8.pt \
  --source usb0 \
  --resolution 1280x720 \
  --trigger_line 60 \
  --save_crossings
```

---

## 🎛️ Parâmetros e Configurações

### Parâmetros Principais

| Parâmetro | Descrição | Tipo | Padrão | Exemplo |
|-----------|-----------|------|--------|---------|
| `--model` | Caminho do modelo YOLO | str | obrigatório | `model-v8.pt` |
| `--source` | Fonte de vídeo/câmera | str | obrigatório | `video.mp4` ou `usb0` |
| `--thresh` | Confiança mínima (0-1) | float | 0.5 | `0.7` |
| `--trigger_line` | Posição da linha vertical (0-100%) | int | 50 | `60` |
| `--save_crossings` | Salvar imagens localmente | flag | False | - |
| `--output_dir` | Pasta para imagens | str | `crossings` | `resultados` |
| `--api_url` | URL da API para POST | str | None | `http://localhost:3000/api` |
| `--resolution` | Resolução do vídeo | str | None | `1280x720` |

### Trigger Line (Linha Vertical)

A trigger line é uma linha **vertical** que detecta objetos cruzando da esquerda→direita ou direita→esquerda:

```bash
# Linha mais à esquerda (30% da largura)
--trigger_line 30

# Linha no centro (padrão)
--trigger_line 50

# Linha mais à direita (70% da largura)
--trigger_line 70
```

### Threshold (Confiança)

Controla a sensibilidade das detecções:

```bash
# Mais detecções (menos rigoroso)
--thresh 0.3

# Balanceado (recomendado)
--thresh 0.5

# Menos detecções (mais rigoroso)
--thresh 0.7
```

### Resolução

Para ajustar performance:

```bash
# Baixa (mais rápido)
--resolution 640x480

# Média
--resolution 1280x720

# Alta (mais lento)
--resolution 1920x1080
```

---

## 📚 Exemplos de Uso

### 1. Desenvolvimento Local (Sem Internet)

Apenas salvar imagens localmente para análise:

```bash
python3 yolo_detect.py \
  --model model-v8.pt \
  --source teste.mp4 \
  --save_crossings \
  --output_dir debug
```

**Resultado:**
- ✅ Imagens salvas em `debug/`
- ✅ Não requer internet
- ✅ Ideal para desenvolvimento

### 2. Teste de Integração com API

Enviar dados para API local + salvar localmente:

```bash
python3 yolo_detect.py \
  --model model-v8.pt \
  --source teste.mp4 \
  --save_crossings \
  --output_dir resultados \
  --api_url http://localhost:3000/api/products
```

**Resultado:**
- ✅ Imagens salvas localmente
- ✅ JSON enviado para API
- ✅ Permite testar integração

### 3. Produção (Webcam + Cloudinary + API)

Sistema completo em produção:

```bash
python3 yolo_detect.py \
  --model model-v8.pt \
  --source usb0 \
  --resolution 1280x720 \
  --trigger_line 60 \
  --api_url https://seu-servidor.com/api/products
```

**Resultado:**
- ✅ Captura em tempo real
- ✅ Upload para Cloudinary
- ✅ Envio para API
- ✅ Sistema completo

### 4. Teste com Modelo Customizado

Usando o modelo do MVP:

```bash
python3 yolo_detect.py \
  --model tracelifemvp/my_model.pt \
  --source teste_esteira_2.mp4 \
  --thresh 0.5 \
  --trigger_line 50 \
  --save_crossings \
  --output_dir teste_crossing
```

### 5. Análise de Performance

Para testar FPS e performance:

```bash
python3 yolo_detect.py \
  --model model-v8.pt \
  --source teste.mp4 \
  --resolution 640x480 \
  --thresh 0.6
```

---

## 📁 Estrutura do Projeto

```
ache-capture-v1/
├── 📄 yolo_detect.py              # Script principal
├── 📄 run_tests.sh                # Script de testes interativo
│
├── 🤖 Modelos YOLO
│   ├── model-v8.pt                # Modelo YOLO v8
│   ├── model-v9.pt                # Modelo YOLO v9
│   ├── model-v14.pt               # Modelo YOLO v14
│   └── tracelifemvp/
│       └── my_model.pt            # Modelo customizado MVP
│
├── 📦 Configuração
│   ├── requirements.txt           # Dependências Python
│   ├── .env                       # Variáveis de ambiente (criar)
│   └── .gitignore                 # Arquivos ignorados no Git
│
├── 📚 Documentação (será unificada)
│   ├── INSTALACAO.md
│   ├── EXEMPLOS_TESTE.md
│   ├── README_TESTES.md
│   ├── CORRECOES_APLICADAS.md
│   └── TESTE_TRIGGER_VERTICAL.md
│
├── 📂 Resultados (criado automaticamente)
│   ├── resultados_video/         # Capturas de vídeos
│   ├── teste_crossing/           # Testes de cruzamento
│   └── crossings/                # Padrão quando não especificado
│
└── 🐍 Ambiente Virtual
    └── venv/                      # NÃO commitar!
```

### Arquivos Gerados Automaticamente

Quando `--save_crossings` está ativo:

```
output_dir/
├── crossing_[UUID]_[timestamp]_[Tipo]_labeled.jpg     # Foto no cruzamento (com labels)
├── analysis_[UUID]_[timestamp]_labeled.jpg            # Frame com bounding boxes
└── analysis_[UUID]_[timestamp]_normal.jpg             # Frame limpo
```

**Exemplo real:**
```
resultados_video/
├── crossing_48d84cd7_20251027_141233_Frasco_Vitamina_labeled.jpg
├── crossing_6cab13e1_20251027_141245_Frasco_Vitamina_labeled.jpg
├── analysis_48d84cd7_20251027_141233_labeled.jpg
└── analysis_48d84cd7_20251027_141233_normal.jpg
```

---

## ✨ Funcionalidades

### 🎯 Detecção e Rastreamento

- **Detecção YOLO**: Suporta v8, v9, v14 e modelos customizados
- **Rastreamento BoT-SORT**: IDs únicos persistentes para cada objeto
- **UUID Universal**: Cada objeto recebe um UUID único
- **Тrajetórias**: Visualização do caminho de cada objeto
- **Contagem**: Quantos objetos estão ativos e quantos cruzaram

### 📸 Captura de Imagens

- **Salvamento Automático**: Foto capturada no momento exato do cruzamento
- **Duas Versões**: Frame normal + Frame com labels/bounding boxes
- **Nomenclatura Inteligente**: UUID + timestamp + tipo da embalagem
- **Qualidade Preservada**: Imagens em resolução original

### 📊 Análise e Dados

- **JSON Estruturado**: Dados prontos para APIs
- **Timestamp Preciso**: Data/hora de cada evento
- **Confiança**: Porcentagem de certeza da detecção
- **Tempo de Vida**: Quanto tempo cada objeto foi rastreado
- **Classe**: Tipo do objeto detectado

### 🌐 Integração

- **API REST**: POST automático para endpoints configuráveis
- **Cloudinary**: Upload assíncrono de imagens
- **Queue System**: Fila para processamento em background
- **Retry Logic**: Tentativas automáticas em caso de falha

### 🎨 Interface Visual

- **Linha Vertical Verde**: Marca a trigger line
- **BBoxes Coloridos**: Cada objeto tem cor única
- **Labels Informativos**: ID, classe, confiança
- **Estatísticas em Tempo Real**: FPS, objetos ativos, total de cruzamentos
- **Траектórias**: Caminho percorrido por cada objeto

### ⌨️ Controles

| Tecla | Ação |
|-------|------|
| `Q` | Sair do programa |
| `S` | Pausar/Continuar |
| `P` | Salvar screenshot manual |

---

## 🔧 Correções e Melhorias

### ✅ Problema 1: Contador Zerava

**Problema Original:**
O contador de objetos que cruzaram a linha voltava para 0 quando objetos saíam da tela.

**Causa:**
```python
# ❌ Código antigo (linha 473)
crossed_objects.discard(track_id)  # Removendo da lista
```

**Solução:**
```python
# ✅ Código novo
# NÃO remover de crossed_objects - manter contagem permanente
# crossed_objects.discard(track_id)  # Linha comentada
```

**Resultado:**
- ✅ Contagem permanente e precisa
- ✅ Logs mostram status: `[✓ CRUZOU]` ou `[✗ não cruzou]`

### ✅ Problema 2: Fotos Sem Labels

**Problema Original:**
Fotos eram salvas SEM os bounding boxes e labels desenhados.

**Causa:**
Foto salva ANTES dos labels serem desenhados no frame.

**Solução:**
Sistema de flag que:
1. Marca objeto para salvar (`save_crossing_photo = True`)
2. Aguarda desenho dos labels
3. Salva foto APÓS labels completos
4. Desmarca flag

**Código:**
```python
# Ao cruzar:
object_registry[track_id]['save_crossing_photo'] = True

# Após desenhar labels:
if object_registry[track_id].get('save_crossing_photo', False):
    cv2.imwrite(output_path, frame.copy())
    object_registry[track_id]['save_crossing_photo'] = False
```

**Resultado:**
- ✅ Todas as fotos têm bounding boxes completos
- ✅ Labels visíveis em todas as capturas

### ✅ Melhoria: Trigger Line Vertical

**Mudança:**
Linha mudou de horizontal (Y) para vertical (X).

**Benefícios:**
- ✅ Detecta objetos em esteiras horizontais
- ✅ Melhor para fluxo esquerda→direita
- ✅ Configurável via `--trigger_line 0-100`

### ✅ Melhoria: Print Detalhado

**Output ao cruzar:**
```
======================================================================
🎯 OBJETO CRUZOU A LINHA!
   Tipo: Frasco_Vitamina
   Veracidade: 87%
   ID: 3 | UUID: 48d84cd7...
   Tempo de vida: 2.5s
======================================================================
📸 Foto salva: crossing_48d84cd7_20251027_141233_Frasco_Vitamina_labeled.jpg
```

**Benefícios:**
- ✅ Visibilidade imediata dos eventos
- ✅ Fácil debugging
- ✅ Auditoria clara

---

## 🐛 Troubleshooting

### Erro: "python: command not found"

```bash
# Use python3 explicitamente
python3 yolo_detect.py --model model-v8.pt --source video.mp4
```

### Erro: "ModuleNotFoundError: No module named 'xxx'"

```bash
# 1. Certifique-se de que o ambiente virtual está ativado
source venv/bin/activate

# 2. Reinstale as dependências
pip install -r requirements.txt

# 3. Se persistir, instale o módulo específico
pip install nome_do_modulo
```

### Erro: "No module named 'lap'"

```bash
# lap precisa ser instalado separadamente
pip install lap
```

### Ambiente Virtual Não Ativa

```bash
# Recrie o ambiente virtual do zero
rm -rf venv
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### Vídeo Não Abre

- Verifique se o caminho está correto
- Confirme que o formato é suportado (mp4, avi, mov, mkv, wmv)
- Tente converter: `ffmpeg -i input.avi output.mp4`

### Vídeo Não Abre Janela

- Certifique-se de não estar usando SSH/terminal remoto
- OpenCV precisa de acesso à interface gráfica
- Em macOS, pode precisar de permissões de acessibilidade

### Nenhum Objeto Detectado

```bash
# Reduza o threshold
--thresh 0.3

# Verifique se o modelo está treinado para as classes do vídeo
```

### FPS Muito Baixo

```bash
# Reduza a resolução
--resolution 640x480

# Ou use modelo menor/mais rápido

# Verifique se GPU está sendo usada
python3 -c "import torch; print(torch.cuda.is_available())"
```

### Objetos Não Cruzam a Linha

- Ajuste `--trigger_line` para onde os objetos passam
- Visualize a linha verde no vídeo
- Teste valores: 30, 50, 70

### Muitas/Poucas Detecções

```bash
# Mais detecções (menos rigoroso)
--thresh 0.3

# Balanceado
--thresh 0.5

# Menos detecções (mais rigoroso)
--thresh 0.7
```

### Imagens Não São Salvas

- Certifique-se de usar `--save_crossings`
- Verifique permissões da pasta de saída
- Confirme que objetos estão cruzando a linha

---

## 📊 Logs e Monitoramento

### Durante Execução

**Novo objeto detectado:**
```
🆕 Novo objeto: ID=1, UUID=a1b2c3d4..., Classe=blister
```

**Objeto cruzou:**
```
🎯 Objeto 1 cruzou a linha! UUID: a1b2c3d4..., Vida: 2.5s
```

**Salvamento:**
```
💾 Imagens salvas em: resultados/
📸 Foto com labels salva: crossing_a1b2c3d4_..._labeled.jpg
```

**Upload:**
```
📤 Enviando análise para Cloudinary...
✅ Análise enfileirada para envio: a1b2c3d4...
```

**Remoção:**
```
🗑️ Objeto 1 removido (timeout). Vida total: 8.3s [✓ CRUZOU]
```

**Estatísticas finais:**
```
FPS médio: 23.45
Total de objetos que cruzaram a linha: 3
```

---

## 🔐 Segurança e Boas Práticas

### Arquivo .gitignore

Certifique-se de ter:

```gitignore
# Ambiente virtual
venv/
tracelifemvp/

# Variáveis de ambiente
.env

# Python
*.pyc
__pycache__/

# Resultados
resultados_video/
crossings/
teste_crossing/
*.jpg
*.png
*.mp4

# IDE
.vscode/
.idea/
*.swp
```

### Variáveis Sensíveis

- ❌ **NUNCA** commite credenciais no código
- ✅ Use arquivo `.env` para credenciais
- ✅ Adicione `.env` ao `.gitignore`
- ✅ Use variáveis de ambiente em produção

---

## 📦 Dependências Principais

| Pacote | Versão | Descrição |
|--------|--------|-----------|
| `python-dotenv` | >= 1.0 | Carregar variáveis de ambiente |
| `cloudinary` | >= 1.40 | Upload de imagens para cloud |
| `opencv-python` | >= 4.8 | Processamento de vídeo |
| `ultralytics` | >= 8.0 | YOLOv8/v9 para detecção |
| `numpy` | >= 1.21 | Operações matemáticas |
| `lap` | >= 0.5 | Algoritmo de tracking |
| `torch` | >= 2.0 | PyTorch para YOLO |
| `requests` | >= 2.28 | Requisições HTTP |

---

## 🎓 Fluxo de Teste Recomendado

### 1. Teste Local Básico

```bash
python3 yolo_detect.py \
  --model model-v8.pt \
  --source video.mp4 \
  --save_crossings
```

✅ Verifique se detecta objetos  
✅ Confirme que salva imagens  
✅ Ajuste threshold se necessário

### 2. Ajuste Trigger Line

```bash
python3 yolo_detect.py \
  --model model-v8.pt \
  --source video.mp4 \
  --trigger_line 60 \
  --save_crossings
```

✅ Observe a linha verde no vídeo  
✅ Ajuste até capturar corretamente  
✅ Teste valores: 30, 50, 70

### 3. Teste com API Local

```bash
python3 yolo_detect.py \
  --model model-v8.pt \
  --source video.mp4 \
  --api_url http://localhost:3000/api/products \
  --save_crossings
```

✅ Confirme que envia JSONs  
✅ Verifique logs da API  
✅ Valide estrutura dos dados

### 4. Teste com Webcam

```bash
python3 yolo_detect.py \
  --model model-v8.pt \
  --source usb0 \
  --resolution 1280x720 \
  --save_crossings
```

✅ Confirme FPS aceitável  
✅ Ajuste resolução se necessário  
✅ Teste em condições reais

### 5. Produção Completa

```bash
python3 yolo_detect.py \
  --model model-v8.pt \
  --source usb0 \
  --resolution 1280x720 \
  --trigger_line 60 \
  --api_url https://seu-servidor.com/api/products
```

✅ Configure .env com Cloudinary  
✅ Teste upload de imagens  
✅ Monitore por tempo prolongado

---

## 💡 Dicas e Truques

### Performance

- Use `--resolution` menor para aumentar FPS
- Modelos v8 são geralmente mais rápidos que v9
- GPU acelera significativamente (CUDA)
- Feche outros aplicativos pesados

### Qualidade

- `--thresh 0.5` é um bom equilíbrio
- Valores muito baixos geram falsos positivos
- Valores muito altos perdem detecções válidas

### Trigger Line

- Observe primeiro onde objetos passam
- Linha deve estar perpendicular ao movimento
- Teste em vídeo antes de usar webcam

### Debug

- Sempre use `--save_crossings` durante testes
- Analise imagens salvas para ajustes
- Monitore logs no terminal
- Use vídeos curtos para testes rápidos

### Organização

- Crie pastas separadas para cada teste
- Use nomes descritivos: `teste_esteira`, `producao_linha1`
- Mantenha backup dos modelos `.pt`
- Documente mudanças de configuração

---

## 🚀 Próximos Passos

Funcionalidades que podem ser implementadas:

- [ ] Dashboard em tempo real (Streamlit/Gradio)
- [ ] Contador por tipo de embalagem
- [ ] Filtro por classe específica
- [ ] Alerta sonoro ao cruzar
- [ ] Exportar relatório CSV/JSON
- [ ] Análise estatística (gráficos)
- [ ] Multi-câmera simultânea
- [ ] Detecção de anomalias
- [ ] Integração com banco de dados
- [ ] Interface web para configuração

---

## 🤝 Contribuições

Este projeto foi desenvolvido para detecção e rastreamento de produtos em linhas de produção.

Para contribuir:
1. Faça fork do repositório
2. Crie uma branch para sua feature
3. Commit suas mudanças
4. Push para a branch
5. Abra um Pull Request

---

## 📞 Suporte

Se encontrar problemas:

1. ✅ Verifique se o ambiente virtual está ativado `(venv)`
2. ✅ Confirme que todas as dependências estão instaladas
3. ✅ Teste com um vídeo pequeno primeiro
4. ✅ Verifique os logs no terminal
5. ✅ Consulte a seção [Troubleshooting](#-troubleshooting)

---

## 📄 Licença

Este projeto é de uso interno. Todos os direitos reservados.

---

## 🎉 Agradecimentos

- **Ultralytics** - Framework YOLO
- **OpenCV** - Processamento de vídeo
- **Cloudinary** - Hospedagem de imagens
- **PyTorch** - Deep Learning

---

**Última atualização:** 27 de Outubro de 2025  
**Versão:** 1.0.0  
**Status:** ✅ Produção
