# 🧪 Guia de Teste - Sistema de Batch Upload

## 📋 Pré-requisitos

1. **Dependências instaladas**:
   ```bash
   pip install -r requirements.txt
   ```

2. **Arquivo `.env` configurado** (opcional, apenas para API):
   ```env
   CLOUDINARY_CLOUD_NAME=seu_cloud_name
   CLOUDINARY_API_KEY=sua_api_key
   CLOUDINARY_API_SECRET=seu_api_secret
   ```

3. **Modelo YOLO disponível**:
   - `model-v14.pt` (ou outro modelo treinado)

---

## 🚀 Testes Recomendados

### Teste 1: Modo Básico (Salvar Localmente - SEM API)
**Objetivo**: Verificar sistema de batch sem upload para Cloudinary

```bash
# Criar pasta de saída
mkdir -p test_batch

# Executar com vídeo ou webcam
python yolo_detect.py \
  --model model-v14.pt \
  --source media/seu_video.mp4 \
  --thresh 0.5 \
  --trigger_line 50 \
  --save_crossings \
  --output_dir test_batch/
```

**O que observar**:
- ✅ Quando objeto cruza: mensagem "⏳ Aguardando batch upload após inatividade"
- ✅ Após 15s sem detecções: "⏱️ 15s sem novas detecções - processando batch..."
- ✅ Mensagens de snapshot criado com hashes
- ✅ Arquivos salvos em `test_batch/` com nomenclatura consistente

**Verificar arquivos**:
```bash
ls -lh test_batch/

# Deve mostrar pares de arquivos:
# crossing_a3f5d8c1_20251028_153045_embalagem_plastico_normal.jpg
# crossing_a3f5d8c1_20251028_153045_embalagem_plastico_labeled.jpg
#          └── mesmo UUID e timestamp ──┘
```

---

### Teste 2: Modo Webcam (Sem API - Teste de Performance)
**Objetivo**: Verificar que FPS mantém-se estável

```bash
python yolo_detect.py \
  --model model-v14.pt \
  --source usb0 \
  --thresh 0.5 \
  --trigger_line 50 \
  --save_crossings \
  --output_dir live_test/
```

**O que observar**:
- ✅ FPS exibido no canto superior esquerdo mantém-se estável (não cai)
- ✅ Quando objetos cruzam, detecção continua fluida
- ✅ Nenhum travamento visível
- ✅ Buffer acumula objetos: "Total no buffer: X objetos"

**Teste de estresse**:
- Passe múltiplos objetos rapidamente pela linha
- FPS deve manter-se em 20-30 (dependendo da máquina)
- Todos os objetos devem ser detectados

---

### Teste 3: Com API Local (Upload Completo)
**Objetivo**: Testar upload para Cloudinary e API

**Passo 1**: Configurar API local (se tiver):
```bash
# Exemplo com Node.js/Express
npm start  # sua API rodando em http://localhost:3000
```

**Passo 2**: Executar com API:
```bash
python yolo_detect.py \
  --model model-v14.pt \
  --source media/seu_video.mp4 \
  --thresh 0.5 \
  --trigger_line 50 \
  --api_url http://localhost:3000/api/products \
  --api_timeout 30
```

**O que observar**:
- ✅ Objetos cruzam → snapshots criados
- ✅ Após 15s: "📦 INICIANDO BATCH UPLOAD - X objetos"
- ✅ Uploads paralelos: "✓ Upload completo: a3f5d8c1 (embalagem_plastico)"
- ✅ Estatísticas: "📊 BATCH CONCLUÍDO - Sucesso: X/X"

**Verificar na API**:
```bash
# Verificar se objetos foram recebidos
curl http://localhost:3000/api/products | jq

# Cada objeto deve ter:
# - uuid único
# - imgNormal e imgLabel diferentes
# - hashNormal e hashLabel diferentes
# - timestamp consistente
```

---

### Teste 4: Upload Unsigned (Cloudinary)
**Objetivo**: Testar upload sem assinatura

```bash
python yolo_detect.py \
  --model model-v14.pt \
  --source media/seu_video.mp4 \
  --thresh 0.5 \
  --trigger_line 50 \
  --api_url http://localhost:3000/api/products \
  --unsigned \
  --upload_preset seu_preset_name
```

**Pré-requisito**: Criar upload preset no Cloudinary Dashboard

---

### Teste 5: Timeout Customizado
**Objetivo**: Ajustar tempo de inatividade

```python
# Editar no código (linha ~121):
BATCH_TIMEOUT = 5.0  # Reduzir para 5 segundos (teste mais rápido)
```

```bash
python yolo_detect.py \
  --model model-v14.pt \
  --source media/seu_video.mp4 \
  --save_crossings \
  --output_dir quick_test/
```

**O que observar**:
- ✅ Batch processa após apenas 5s de inatividade
- ✅ Útil para vídeos curtos ou testes rápidos

---

### Teste 6: Verificar Consistência de Hashes
**Objetivo**: Garantir que fotos são únicas e consistentes

```bash
# Executar teste
python yolo_detect.py \
  --model model-v14.pt \
  --source media/seu_video.mp4 \
  --save_crossings \
  --output_dir hash_test/

# Após execução, verificar hashes
cd hash_test/

# Calcular hash de um arquivo
md5 crossing_*_normal.jpg
```

**Verificar**:
1. Hash calculado manualmente deve bater com hash do log
2. Arquivos `*_normal.jpg` e `*_labeled.jpg` com mesmo UUID devem ser pares
3. Hashes diferentes entre normal e labeled (são imagens diferentes)

---

### Teste 7: Encerramento Forçado
**Objetivo**: Verificar processamento final

```bash
python yolo_detect.py \
  --model model-v14.pt \
  --source usb0 \
  --save_crossings \
  --output_dir abort_test/
```

**Passo**:
1. Deixar 2-3 objetos cruzarem
2. Pressionar `Ctrl+C` ANTES dos 15s
3. Sistema deve processar batch pendente

**O que observar**:
- ✅ Mensagem: "⚠️ Existem X snapshots pendentes no buffer"
- ✅ "Processando batch final antes de encerrar..."
- ✅ Todos os objetos salvos/enviados
- ✅ Estatísticas finais exibidas

---

## 📊 Checklist de Validação

Após os testes, verificar:

- [ ] **FPS estável**: Não cai durante cruzamento de linha
- [ ] **Zero travamentos**: Loop de detecção nunca trava
- [ ] **Fotos vinculadas**: Pares normal/labeled com mesmo UUID
- [ ] **Hashes corretos**: MD5 bate com arquivo
- [ ] **Batch funciona**: Processa após 15s de inatividade
- [ ] **Upload paralelo**: Múltiplos objetos processados simultaneamente
- [ ] **Estatísticas corretas**: Total uploads = sucessos + falhas
- [ ] **Cleanup final**: Batch pendente processado ao encerrar
- [ ] **Logs informativos**: Cada etapa é claramente registrada

---

## 🐛 Troubleshooting

### Problema: "Não foi possível resolver a importação picamera2"
**Solução**: IGNORAR - é esperado. Só funciona em Raspberry Pi.

### Problema: Batch nunca processa
**Diagnóstico**:
```python
# Adicionar debug temporário após linha 520
print(f'DEBUG: last_detection_time = {last_detection_time}')
print(f'DEBUG: pending_uploads = {len(pending_uploads)}')
```

**Causas possíveis**:
- Timer não está sendo atualizado
- Objetos não estão cruzando a linha
- BATCH_TIMEOUT muito alto

### Problema: Upload falha com erro 401
**Causa**: Credenciais Cloudinary inválidas  
**Solução**: Verificar arquivo `.env`

### Problema: API retorna 500
**Causa**: JSON inválido ou API offline  
**Solução**: Testar API manualmente:
```bash
curl -X POST http://localhost:3000/api/products \
  -H "Content-Type: application/json" \
  -d '{"uuid":"test","tipo":"test"}'
```

### Problema: Hashes não batem
**Causa**: Arquivo foi modificado após criação  
**Solução**: Verificar que `.copy()` está sendo usado corretamente

---

## 📈 Métricas de Sucesso

### Performance Esperada (Máquina Média)
- **FPS com webcam**: 25-30 fps constante
- **FPS durante batch**: Sem impacto (batch em thread separada)
- **Tempo de snapshot**: < 1ms
- **Tempo de batch (10 objetos)**: 10-15s paralelo

### Taxa de Sucesso
- **Detecção**: 100% dos objetos na linha
- **Snapshot**: 100% (travado no código)
- **Upload**: 95%+ (depende de rede/Cloudinary)

---

## ✅ Teste Final Completo

```bash
# Teste completo end-to-end
python yolo_detect.py \
  --model model-v14.pt \
  --source media/demo_video.mp4 \
  --thresh 0.5 \
  --trigger_line 50 \
  --api_url http://localhost:3000/api/products \
  --save_crossings \
  --output_dir final_test/ \
  --api_timeout 30

# Aguardar conclusão
# Verificar:
# 1. Arquivos em final_test/
# 2. Objetos na API
# 3. Imagens no Cloudinary
# 4. Estatísticas no terminal
```

---

## 📝 Próximos Passos

Após validação, considerar:

1. **Ajustar timeout**: Alterar `BATCH_TIMEOUT` conforme necessidade
2. **Aumentar workers**: Alterar `max_workers=5` para mais paralelismo
3. **Adicionar retry**: Implementar tentativa automática em caso de falha
4. **Monitoramento**: Logs mais detalhados ou integração com Sentry
5. **Otimização**: Compressão de imagens antes do upload

---

## 📞 Suporte

Se encontrar problemas:
1. Verificar logs no terminal (muito verbosos agora)
2. Consultar `CHANGELOG_BATCH_SYSTEM.md`
3. Comparar com `ANTES_VS_DEPOIS.md`
4. Abrir issue com logs completos
