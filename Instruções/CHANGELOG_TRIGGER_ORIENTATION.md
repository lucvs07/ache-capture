# 🔄 Changelog - Orientação da Trigger Line

## Data: 1 de novembro de 2025

---

## 🎯 Resumo

Adicionada funcionalidade para **alternar entre trigger line horizontal e vertical** durante a execução do script de testes (`run_tests.sh`), permitindo maior flexibilidade na configuração do sistema conforme o setup da esteira ou fluxo de objetos.

---

## ✨ Novas Funcionalidades

### 1. **Novo Parâmetro CLI: `--trigger_orientation`**

```bash
--trigger_orientation [horizontal|vertical]
```

**Opções:**
- `horizontal` (padrão): Linha horizontal que detecta objetos cruzando de **cima para baixo** ou **baixo para cima**
- `vertical`: Linha vertical que detecta objetos cruzando da **esquerda para direita** ou **direita para esquerda**

**Exemplo de uso:**
```bash
# Linha horizontal (padrão)
python yolo_detect.py --model model-v14.pt --source usb0 \
  --trigger_line 50 --trigger_orientation horizontal

# Linha vertical
python yolo_detect.py --model model-v14.pt --source usb0 \
  --trigger_line 30 --trigger_orientation vertical
```

---

### 2. **Menu Interativo no `run_tests.sh`**

Ao executar `./run_tests.sh`, o usuário agora vê:

```
Escolha a orientação da trigger line:
1) Horizontal (detecta objetos cruzando de cima para baixo)
2) Vertical (detecta objetos cruzando da esquerda para direita)

Orientação (1-2, padrão: 1): _
```

A escolha é aplicada **automaticamente** a todas as opções de teste (webcam, vídeo, API, etc).

---

## 🔧 Mudanças Técnicas

### **yolo_detect.py**

#### **1. Novo Argumento de Linha de Comando**
```python
parser.add_argument('--trigger_orientation', 
    help='Trigger line orientation: "horizontal" or "vertical"', 
    type=str, default='horizontal', choices=['horizontal', 'vertical'])
```

#### **2. Cálculo Dinâmico da Posição da Linha**
```python
# Calcular baseado na orientação
if args.trigger_orientation == 'horizontal':
    trigger_y = int((args.trigger_line / 100) * frame.shape[0])
    trigger_x = None
else:  # vertical
    trigger_x = int((args.trigger_line / 100) * frame.shape[1])
    trigger_y = None
```

#### **3. Detecção de Cruzamento Adaptável**
```python
if args.trigger_orientation == 'horizontal':
    # Horizontal: detecta cruzamento no eixo Y
    prev_y = position_history[-2][1]
    curr_y = center_y
    crossed = (prev_y < trigger_y <= curr_y) or (prev_y > trigger_y >= curr_y)
else:
    # Vertical: detecta cruzamento no eixo X
    prev_x = position_history[-2][0]
    curr_x = center_x
    crossed = (prev_x < trigger_x <= curr_x) or (prev_x > trigger_x >= curr_x)
```

#### **4. Renderização Diferenciada**
```python
if args.trigger_orientation == 'horizontal':
    # Linha horizontal
    cv2.line(frame, (0, trigger_y), (frame.shape[1], trigger_y), (0, 255, 0), 3)
    cv2.putText(frame, 'TRIGGER LINE (HORIZONTAL)', (10, trigger_y - 10), ...)
else:
    # Linha vertical
    cv2.line(frame, (trigger_x, 0), (trigger_x, frame.shape[0]), (0, 255, 0), 3)
    cv2.putText(frame, 'TRIGGER LINE (VERTICAL)', (trigger_x + 10, 30), ...)
```

#### **5. Mensagem de Configuração Atualizada**
```python
if args.trigger_orientation == 'horizontal':
    print(f'Trigger Line: {args.trigger_line}% da altura (linha horizontal)')
else:
    print(f'Trigger Line: {args.trigger_line}% da largura (linha vertical)')
print(f'Orientação da linha: {args.trigger_orientation}')
```

---

### **run_tests.sh**

#### **1. Seleção de Orientação no Início**
```bash
# Perguntar orientação da trigger line
echo "Escolha a orientação da trigger line:"
echo "1) Horizontal (detecta objetos cruzando de cima para baixo)"
echo "2) Vertical (detecta objetos cruzando da esquerda para direita)"
read -p "Orientação (1-2, padrão: 1): " ORIENTATION_CHOICE

case $ORIENTATION_CHOICE in
    2)
        TRIGGER_ORIENTATION="vertical"
        ;;
    *)
        TRIGGER_ORIENTATION="horizontal"
        ;;
esac
```

#### **2. Aplicação em Todos os Testes**
Todas as 7 opções do menu agora incluem:
```bash
--trigger_orientation "$TRIGGER_ORIENTATION"
```

---

## 📊 Comparação: Horizontal vs Vertical

| Aspecto | Horizontal | Vertical |
|---------|-----------|----------|
| **Linha desenhada** | De lado a lado | De cima a baixo |
| **Eixo detectado** | Y (altura) | X (largura) |
| **Movimento detectado** | ↕ (vertical) | ↔ (horizontal) |
| **Percentual refere-se a** | Altura do frame | Largura do frame |
| **Uso recomendado** | Esteiras horizontais | Esteiras verticais |
| **Exemplo de posição** | 50% = meio da altura | 50% = meio da largura |

---

## 🎨 Visualização

### **Modo Horizontal (padrão)**
```
┌─────────────────────────┐
│                         │
│    🟢 Objeto           │
│         ↓               │
│━━━━━━━━━━━━━━━━━━━━━━━│ ← Trigger Line (50%)
│         ↓               │
│    🟢 Objeto (cruzou)  │
│                         │
└─────────────────────────┘
```

### **Modo Vertical**
```
┌──────────┃──────────────┐
│          ┃              │
│  🟢→→→→→┃→→→🟢          │
│  Obj     ┃   Obj        │
│          ┃   (cruzou)   │
│          ┃              │
└──────────┃──────────────┘
           ↑
    Trigger Line (30%)
```

---

## 📝 Exemplos de Uso

### **Esteira Horizontal com Objetos Descendo**
```bash
./run_tests.sh
# Selecionar: 1 (Horizontal)
# Selecionar opção de teste: 2 (Webcam + salvamento)
```

### **Esteira Vertical com Objetos Indo da Esquerda para Direita**
```bash
./run_tests.sh
# Selecionar: 2 (Vertical)
# Selecionar opção de teste: 6 (Teste completo)
# Definir posição: 30 (30% da largura)
```

### **Comando Manual**
```bash
# Horizontal no centro da altura
python yolo_detect.py --model model-v14.pt --source usb0 \
  --trigger_line 50 --trigger_orientation horizontal

# Vertical 30% da largura (próximo à esquerda)
python yolo_detect.py --model model-v14.pt --source video.mp4 \
  --trigger_line 30 --trigger_orientation vertical
```

---

## ✅ Testes Realizados

- ✅ Compilação sem erros (apenas aviso esperado de picamera2)
- ✅ Parâmetro `--trigger_orientation` funcionando corretamente
- ✅ Menu interativo do `run_tests.sh` implementado
- ✅ Todas as 7 opções do menu incluem novo parâmetro
- ✅ Cálculo de posição correto para ambas orientações
- ✅ Detecção de cruzamento funcionando em ambos os eixos
- ✅ Renderização visual diferenciada
- ✅ Documentação técnica atualizada

---

## 📚 Arquivos Modificados

1. **yolo_detect.py**
   - Linha 88-90: Novo argumento `--trigger_orientation`
   - Linha 433-438: Mensagem de configuração atualizada
   - Linha 473-481: Cálculo dinâmico da posição da linha
   - Linha 564-576: Lógica de detecção de cruzamento adaptável
   - Linha 743-753: Renderização diferenciada da linha

2. **run_tests.sh**
   - Linha 82-98: Seleção de orientação no início
   - Todas as opções 1-7: Inclusão do parâmetro `--trigger_orientation`

3. **DOCUMENTACAO_TECNICA.md**
   - Linha 13: Atualização da visão geral
   - Linha 154-201: Seção expandida sobre detecção de cruzamento
   - Linha 598: Parâmetro adicionado à lista CLI
   - Linha 843-877: Casos de uso atualizados com exemplos

4. **CHANGELOG_TRIGGER_ORIENTATION.md** (NOVO)
   - Documentação completa das mudanças

---

## 🚀 Próximos Passos

Possíveis melhorias futuras:
- [ ] Adicionar suporte a linhas diagonais
- [ ] Permitir múltiplas trigger lines simultaneamente
- [ ] Salvar configuração de orientação em arquivo de config
- [ ] Visualização em tempo real da zona de detecção

---

## 📞 Suporte

Para dúvidas ou problemas, consulte:
- **DOCUMENTACAO_TECNICA.md** - Documentação técnica completa
- **GUIA_DE_TESTES.md** - Guia de testes passo a passo
- **README.md** - Informações gerais do projeto

---

**Desenvolvido por:** Equipe Ache Capture V2  
**Data de Release:** 1 de novembro de 2025  
**Versão:** 2.1 - Trigger Line com Orientação Configurável
