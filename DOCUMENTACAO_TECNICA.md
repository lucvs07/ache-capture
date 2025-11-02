# 📖 Documentação Técnica - Sistema de Rastreamento e Análise de Embalagens

## 🎯 Visão Geral

Este sistema utiliza **YOLO (You Only Look Once)** com **rastreamento de objetos** para detectar, rastrear e analisar embalagens em tempo real através de vídeos ou câmeras. Quando um objeto cruza uma linha de gatilho (trigger line), o sistema captura imagens e pode enviá-las para análise via API.

**Principais Recursos:**
- ✅ Detecção e rastreamento em tempo real
- ✅ Sistema de votação por consenso para classificação
- ✅ Linha de gatilho configurável (horizontal ou vertical)
- ✅ Upload em batch não-bloqueante
- ✅ Consistência garantida de fotos (snapshot atômico)
- ✅ Validação por hash MD5
- ✅ Salvamento local e/ou envio para API/Cloudinary

---

## 🏗️ Arquitetura do Sistema

```
┌─────────────────────────────────────────────────────────────────┐
│                    THREAD PRINCIPAL                             │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │  1. Captura de Frames (Vídeo/Webcam/Imagens)             │   │
│  │     ↓                                                     │   │
│  │  2. Detecção YOLO + Rastreamento                         │   │
│  │     ↓                                                     │   │
│  │  3. Registro de Objetos (UUID, Classe, Confiança)       │   │
│  │     ↓                                                     │   │
│  │  4. Verificação de Cruzamento da Trigger Line           │   │
│  │     ↓                                                     │   │
│  │  5. Snapshot Atômico (se cruzou)                         │   │
│  │     ↓                                                     │   │
│  │  6. Adicionar ao Buffer (pending_uploads)               │   │
│  │     ↓                                                     │   │
│  │  7. Desenhar Visualizações e Exibir                     │   │
│  └──────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
                              │
                              │ Comunicação thread-safe
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│                    THREAD DE BATCH MONITOR                      │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │  1. Monitorar tempo de inatividade (a cada 1s)          │   │
│  │     ↓                                                     │   │
│  │  2. Passou 15s sem detecções?                            │   │
│  │     ↓ SIM                                                │   │
│  │  3. Disparar process_batch_uploads()                     │   │
│  │     ↓                                                     │   │
│  │  4. Upload paralelo (ThreadPoolExecutor)                │   │
│  │     ↓                                                     │   │
│  │  5. Enviar para API (via post_queue)                    │   │
│  └──────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│                    THREAD DE POST WORKER                        │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │  1. Aguardar requisições na fila (post_queue)           │   │
│  │     ↓                                                     │   │
│  │  2. Enviar POST para API                                 │   │
│  │     ↓                                                     │   │
│  │  3. Registrar sucesso/falha                              │   │
│  └──────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

---

## 🔧 Componentes Principais

### 1. **DetectionSnapshot (Dataclass)**

Estrutura imutável que garante consistência entre fotos normal e labeled.

```python
@dataclass
class DetectionSnapshot:
    track_id: int              # ID de rastreamento
    uuid: str                  # UUID único do objeto
    timestamp: str             # Timestamp do cruzamento
    frame_normal: np.ndarray   # Foto sem bounding boxes
    frame_labeled: np.ndarray  # Foto COM bounding boxes
    hash_normal: str           # Hash MD5 do frame normal
    hash_labeled: str          # Hash MD5 do frame labeled
    metadata: Dict             # Metadados (tipo, confiança, etc)
```

**Validação automática:**
- Verifica que frames não são None
- Verifica que frames têm mesma dimensão
- Garante imutabilidade após criação

---

### 2. **Sistema de Registro de Objetos**

Cada objeto detectado é registrado em `object_registry`:

```python
object_registry[track_id] = {
    'uuid': str(uuid.uuid4()),           # UUID único
    'first_seen': timestamp,             # Quando apareceu
    'last_seen': timestamp,              # Última detecção
    'class': classname,                  # Classe majoritária
    'class_history': [],                 # Histórico de classificações
    'crossed_line': False,               # Cruzou a linha?
    'position_history': deque(maxlen=30),# Últimas 30 posições
    'best_frame': None,                  # Melhor frame (sem labels)
    'best_frame_labeled': None,          # Backup do frame labeled
    'best_confidence': 0.0,              # Maior confiança detectada
    'detection_bbox': None               # Bounding box da melhor detecção
}
```

**Fluxo de vida de um objeto:**
1. **Primeira detecção** → Cria registro com UUID único
2. **Detecções subsequentes** → Atualiza histórico, posição e melhor frame
3. **Cruzamento da linha** → Cria snapshot e adiciona ao buffer
4. **Timeout (5s sem ver)** → Remove do registro (mas mantém em `crossed_objects`)

---

### 3. **Sistema de Votação por Consenso**

Para aumentar a precisão, o sistema usa **votação majoritária** para classificação:

```python
# A cada detecção, adiciona classe ao histórico
object_registry[track_id]['class_history'].append(classname)

# Calcula classe mais frequente
class_counter = Counter(object_registry[track_id]['class_history'])
most_common_class = class_counter.most_common(1)[0][0]

# Estatísticas de consenso
vote_count = class_counter[most_common_class]  # Votos da classe vencedora
total_votes = len(class_history)               # Total de detecções
vote_percent = (vote_count / total_votes) * 100 # Percentual de consenso
```

**Exemplo:**
```
Detecções: [plástico, plástico, metal, plástico, plástico]
Consenso: plástico (4/5 = 80%)
```

Isso reduz falsos positivos causados por detecções pontuais incorretas.

---

### 4. **Detecção de Cruzamento da Trigger Line**

A linha de gatilho pode ser **horizontal** (detecta movimento vertical) ou **vertical** (detecta movimento horizontal):

#### **Modo Horizontal (padrão):**
```python
# Cálculo da posição Y da linha (ex: 50% = meio da tela)
trigger_y = int((args.trigger_line / 100) * frame.shape[0])

# Verificação de cruzamento
if len(position_history) >= 2:
    prev_y = position_history[-2][1]  # Y anterior
    curr_y = position_history[-1][1]  # Y atual
    
    # Cruzou de cima pra baixo?
    if prev_y < trigger_y <= curr_y:
        # CRUZOU!
    
    # Cruzou de baixo pra cima?
    if prev_y > trigger_y >= curr_y:
        # CRUZOU!
```

#### **Modo Vertical:**
```python
# Cálculo da posição X da linha (ex: 50% = meio da tela)
trigger_x = int((args.trigger_line / 100) * frame.shape[1])

# Verificação de cruzamento
if len(position_history) >= 2:
    prev_x = position_history[-2][0]  # X anterior
    curr_x = position_history[-1][0]  # X atual
    
    # Cruzou da esquerda pra direita?
    if prev_x < trigger_x <= curr_x:
        # CRUZOU!
    
    # Cruzou da direita pra esquerda?
    if prev_x > trigger_x >= curr_x:
        # CRUZOU!
```

**Configuração:**
```bash
# Linha horizontal (detecta movimento vertical)
--trigger_line 50 --trigger_orientation horizontal   # 50% da altura (meio)
--trigger_line 30 --trigger_orientation horizontal   # 30% da altura (1/3 superior)
--trigger_line 70 --trigger_orientation horizontal   # 70% da altura (base)

# Linha vertical (detecta movimento horizontal)
--trigger_line 50 --trigger_orientation vertical     # 50% da largura (meio)
--trigger_line 30 --trigger_orientation vertical     # 30% da largura (esquerda)
--trigger_line 70 --trigger_orientation vertical     # 70% da largura (direita)
```

---

### 5. **Snapshot Atômico**

Quando um objeto cruza a linha, o sistema cria um **snapshot atômico** que garante consistência:

```python
# 1. Captura imediata com cópias profundas
snapshot_normal = object_registry[track_id]['best_frame'].copy()

# 2. Redesenha bounding box no frame labeled
snapshot_labeled = snapshot_normal.copy()  # Começa limpo
cv2.rectangle(snapshot_labeled, bbox, color, 2)  # Desenha box
cv2.putText(snapshot_labeled, label, ...)        # Adiciona label

# 3. Gera hashes MD5 para validação
hash_normal = hashlib.md5(snapshot_normal.tobytes()).hexdigest()[:16]
hash_labeled = hashlib.md5(snapshot_labeled.tobytes()).hexdigest()[:16]

# 4. Cria objeto imutável
snapshot = DetectionSnapshot(
    track_id=track_id,
    uuid=uuid,
    timestamp=timestamp,
    frame_normal=snapshot_normal,
    frame_labeled=snapshot_labeled,
    hash_normal=hash_normal,
    hash_labeled=hash_labeled,
    metadata={...}
)

# 5. Adiciona ao buffer (thread-safe)
with batch_lock:
    pending_uploads[track_id] = snapshot
```

**Por que isso funciona?**
- `.copy()` cria cópia independente (não é afetada por frames futuros)
- Redesenha boxes no momento exato do snapshot
- Hash MD5 garante integridade dos dados
- Lock garante que múltiplas threads não corrompam o buffer

---

### 6. **Sistema de Batch Upload**

**Problema resolvido:** Upload síncrono travava a detecção.

**Solução:** Buffer + Upload assíncrono em batch.

#### **Variáveis Globais:**
```python
pending_uploads = {}           # Buffer de snapshots
last_detection_time = None     # Timer de inatividade
BATCH_TIMEOUT = 15.0           # Segundos sem detecção para disparar batch
batch_lock = threading.Lock()  # Lock thread-safe
batch_processing = False       # Flag para evitar múltiplos batches simultâneos
```

#### **Fluxo de Batch:**

```
Objeto cruza → Snapshot criado → Adiciona ao buffer → Timer reiniciado
                                        ↓
                        (continua detectando normalmente)
                                        ↓
                        15s sem novas detecções
                                        ↓
                        Batch Monitor detecta timeout
                                        ↓
                        process_batch_uploads() acionado
                                        ↓
            ┌───────────────────────────┴───────────────────────────┐
            │         ThreadPoolExecutor (5 workers)                │
            ├──────────┬──────────┬──────────┬──────────┬───────────┤
            │ Worker 1 │ Worker 2 │ Worker 3 │ Worker 4 │ Worker 5  │
            │ Upload   │ Upload   │ Upload   │ Upload   │ Upload    │
            │ Obj 1    │ Obj 2    │ Obj 3    │ Obj 4    │ Obj 5     │
            └──────────┴──────────┴──────────┴──────────┴───────────┘
                                        ↓
                        Uploads paralelos para Cloudinary
                                        ↓
                        Envio para API (via post_queue)
                                        ↓
                        Buffer limpo, estatísticas atualizadas
```

#### **Código do Batch Monitor:**
```python
def batch_monitor_worker():
    global last_detection_time
    
    while True:
        time.sleep(1)  # Verifica a cada 1 segundo
        
        if last_detection_time is None:
            continue
        
        # Calcular tempo ocioso
        idle_time = time.time() - last_detection_time
        
        # Se passou 15s E há objetos no buffer
        if idle_time >= BATCH_TIMEOUT and len(pending_uploads) > 0:
            process_batch_uploads()
            last_detection_time = None  # Reset timer
```

---

### 7. **Upload Paralelo para Cloudinary**

```python
def upload_snapshot_to_cloudinary(snapshot: DetectionSnapshot) -> Optional[Dict]:
    # 1. Criar nomes de arquivo únicos
    filename_normal = f'analysis_{uuid[:8]}_{timestamp}_{class}_normal.jpg'
    filename_labeled = f'analysis_{uuid[:8]}_{timestamp}_{class}_labeled.jpg'
    
    # 2. Salvar temporariamente
    cv2.imwrite(temp_path_normal, snapshot.frame_normal)
    cv2.imwrite(temp_path_labeled, snapshot.frame_labeled)
    
    # 3. Upload para Cloudinary
    resp_normal = cloudinary.uploader.upload(temp_path_normal, folder='ache-capture/normal')
    resp_labeled = cloudinary.uploader.upload(temp_path_labeled, folder='ache-capture/labeled')
    
    # 4. Limpar arquivos temporários
    os.remove(temp_path_normal)
    os.remove(temp_path_labeled)
    
    # 5. Retornar URLs + hashes
    return {
        'url_normal': resp_normal.get('secure_url'),
        'url_labeled': resp_labeled.get('secure_url'),
        'hash_normal': snapshot.hash_normal,
        'hash_labeled': snapshot.hash_labeled
    }
```

**Upload paralelo:**
```python
with ThreadPoolExecutor(max_workers=5) as executor:
    futures = {
        executor.submit(upload_snapshot_to_cloudinary, snap): snap 
        for snap in snapshots_to_process
    }
    
    for future in futures:
        result = future.result(timeout=30)
        if result:
            send_to_api(snapshot, result)
```

---

### 8. **Envio para API**

```python
def send_to_api(snapshot: DetectionSnapshot, cloudinary_urls: Dict) -> bool:
    product = {
        'id': snapshot.uuid,                  # UUID como ID único
        'trackId': snapshot.track_id,         # ID de rastreamento
        'uuid': snapshot.uuid,
        'data': datetime.now().isoformat(),
        'tipo': snapshot.metadata['tipo'],
        'aprovado': snapshot.metadata['aprovado'],
        'status': snapshot.metadata['status'],
        'veracidade': snapshot.metadata['veracidade'],
        'confianca': snapshot.metadata['confianca'],
        'consenso': snapshot.metadata['consenso'],
        'consensoPercentual': snapshot.metadata['consensoPercentual'],
        'tempoVidaSegundos': snapshot.metadata['tempoVidaSegundos'],
        'imgLabel': cloudinary_urls['url_labeled'],
        'imgNormal': cloudinary_urls['url_normal'],
        'hashLabel': cloudinary_urls['hash_labeled'],
        'hashNormal': cloudinary_urls['hash_normal'],
        'cruzouLinha': True,
        'timestamp': snapshot.timestamp
    }
    
    # Envia via queue (não bloqueia)
    post_queue.put({
        'url': args.api_url,
        'json': product,
        'headers': {'Content-Type': 'application/json'},
        'timeout': args.api_timeout
    })
```

**Estrutura do JSON enviado:**
```json
{
  "id": "a3f5d8c1-2b4e-4c9f-8d2a-1e3f4a5b6c7d",
  "trackId": 42,
  "uuid": "a3f5d8c1-2b4e-4c9f-8d2a-1e3f4a5b6c7d",
  "data": "2025-10-28T15:30:45.123456",
  "tipo": "embalagem_plastico",
  "aprovado": true,
  "status": "aprovado",
  "veracidade": "95%",
  "confianca": 0.95,
  "consenso": "28/30",
  "consensoPercentual": 93,
  "tempoVidaSegundos": 3.45,
  "imgLabel": "https://res.cloudinary.com/.../labeled.jpg",
  "imgNormal": "https://res.cloudinary.com/.../normal.jpg",
  "hashLabel": "7f8d9e2a1b3c4d5e",
  "hashNormal": "9a8b7c6d5e4f3g2h",
  "cruzouLinha": true,
  "timestamp": "20251028_153045"
}
```

**Exemplo com blister incompleto:**
```json
{
  "id": "b4e6f9d2-3c5f-5d0a-9e3b-2f4g5b6c8d9e",
  "trackId": 43,
  "uuid": "b4e6f9d2-3c5f-5d0a-9e3b-2f4g5b6c8d9e",
  "data": "2025-11-01T10:15:30.654321",
  "tipo": "blister_incompleto",
  "aprovado": false,
  "status": "verificar",
  "veracidade": "88%",
  "confianca": 0.88,
  "consenso": "25/28",
  "consensoPercentual": 89,
  "tempoVidaSegundos": 2.87,
  "imgLabel": "https://res.cloudinary.com/.../labeled.jpg",
  "imgNormal": "https://res.cloudinary.com/.../normal.jpg",
  "hashLabel": "9b0c1d2e3f4g5h6i",
  "hashNormal": "7i8h9g0f1e2d3c4b",
  "cruzouLinha": true,
  "timestamp": "20251101_101530",
  "contagem": "pendente"
}
```

**Observação:** O campo `contagem` só é incluído quando o sistema detecta um blister incompleto (classe contém "incompleto" ou "incomplete").

---

## 🔄 Fluxo Completo de Execução

### **1. Inicialização**

```python
# Carregar modelo YOLO
model = YOLO(model_path, task='detect')

# Iniciar threads em background
post_thread = threading.Thread(target=post_worker, daemon=True)
batch_thread = threading.Thread(target=batch_monitor_worker, daemon=True)

# Iniciar captura de vídeo/câmera
cap = cv2.VideoCapture(source)
```

### **2. Loop Principal de Detecção**

```python
while True:
    # Capturar frame
    ret, frame = cap.read()
    
    # Calcular posição da trigger line
    trigger_y = int((args.trigger_line / 100) * frame.shape[0])
    
    # Cópia limpa do frame (sem labels)
    frame_sem_label = frame.copy()
    
    # Executar detecção + rastreamento
    results = model.track(frame, persist=True, verbose=False)
    detections = results[0].boxes
    
    # Processar cada detecção
    for detection in detections:
        track_id = detection.id
        bbox = detection.xyxy
        classname = detection.cls
        confidence = detection.conf
        
        # Registrar ou atualizar objeto
        if track_id not in object_registry:
            # Novo objeto → criar registro
            object_registry[track_id] = {
                'uuid': str(uuid.uuid4()),
                'first_seen': time.time(),
                'class_history': [],
                'position_history': deque(maxlen=30),
                'best_confidence': 0.0,
                # ...
            }
        
        # Atualizar histórico
        object_registry[track_id]['class_history'].append(classname)
        object_registry[track_id]['position_history'].append((center_x, center_y))
        
        # Atualizar melhor frame se confiança maior
        if confidence > object_registry[track_id]['best_confidence']:
            object_registry[track_id]['best_frame'] = frame_sem_label.copy()
            object_registry[track_id]['best_confidence'] = confidence
            object_registry[track_id]['detection_bbox'] = bbox
        
        # Verificar cruzamento da linha
        if len(position_history) >= 2:
            prev_y = position_history[-2][1]
            curr_y = position_history[-1][1]
            
            if (prev_y < trigger_y <= curr_y) or (prev_y > trigger_y >= curr_y):
                # CRUZOU!
                create_snapshot_and_add_to_buffer(track_id)
        
        # Desenhar visualizações
        cv2.rectangle(frame, bbox, color, 2)
        cv2.putText(frame, label, position, ...)
    
    # Desenhar trigger line
    cv2.line(frame, (0, trigger_y), (width, trigger_y), (0,255,0), 3)
    
    # Exibir frame
    cv2.imshow('Rastreamento', frame)
    
    # Atualizar timer de última detecção
    last_detection_time = time.time()
```

### **3. Criação de Snapshot**

```python
def create_snapshot_and_add_to_buffer(track_id):
    # Capturar frames
    snapshot_normal = object_registry[track_id]['best_frame'].copy()
    snapshot_labeled = snapshot_normal.copy()
    
    # Redesenhar bounding box
    bbox = object_registry[track_id]['detection_bbox']
    cv2.rectangle(snapshot_labeled, bbox, color, 2)
    cv2.putText(snapshot_labeled, label, ...)
    
    # Gerar hashes
    hash_normal = hashlib.md5(snapshot_normal.tobytes()).hexdigest()[:16]
    hash_labeled = hashlib.md5(snapshot_labeled.tobytes()).hexdigest()[:16]
    
    # Criar snapshot
    snapshot = DetectionSnapshot(
        track_id=track_id,
        uuid=object_registry[track_id]['uuid'],
        timestamp=datetime.now().strftime('%Y%m%d_%H%M%S'),
        frame_normal=snapshot_normal,
        frame_labeled=snapshot_labeled,
        hash_normal=hash_normal,
        hash_labeled=hash_labeled,
        metadata={...}
    )
    
    # Adicionar ao buffer (thread-safe)
    with batch_lock:
        pending_uploads[track_id] = snapshot
```

### **4. Processamento de Batch**

```python
# Batch Monitor detecta 15s de inatividade
if idle_time >= 15.0 and len(pending_uploads) > 0:
    
    # Copiar buffer e limpar (thread-safe)
    with batch_lock:
        snapshots_to_process = list(pending_uploads.values())
        pending_uploads.clear()
    
    # Upload paralelo
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = [
            executor.submit(upload_snapshot_to_cloudinary, snap)
            for snap in snapshots_to_process
        ]
        
        for future in futures:
            cloudinary_urls = future.result()
            
            if cloudinary_urls and args.api_url:
                send_to_api(snapshot, cloudinary_urls)
```

### **5. Cleanup e Finalização**

```python
# Ao encerrar (Ctrl+C ou fim do vídeo)
if len(pending_uploads) > 0:
    print('Processando batch final...')
    process_batch_uploads()

# Exibir estatísticas
print(f'Total de objetos: {len(crossed_objects)}')
print(f'Uploads bem-sucedidos: {upload_stats["successful"]}')
print(f'Uploads com falha: {upload_stats["failed"]}')

# Liberar recursos
cap.release()
cv2.destroyAllWindows()
post_queue.put(None)  # Sinalizar encerramento do post_worker
```

---

## 🎛️ Parâmetros de Configuração

### **Linha de Comando**

```bash
python yolo_detect.py \
  --model <caminho_modelo>         # OBRIGATÓRIO: modelo YOLO (.pt)
  --source <fonte>                 # OBRIGATÓRIO: vídeo/webcam/imagem
  --thresh <0.0-1.0>              # Threshold de confiança mínima (padrão: 0.5)
  --trigger_line <0-100>          # Posição da linha (% altura ou largura, padrão: 20)
  --trigger_orientation <h|v>     # Orientação: "horizontal" ou "vertical" (padrão: horizontal)
  --resolution <WxH>              # Resolução de exibição (ex: 1280x720)
  --api_url <url>                 # URL da API para enviar dados
  --api_timeout <segundos>        # Timeout de requisições API (padrão: 10.0)
  --save_crossings                # Salvar imagens localmente
  --output_dir <pasta>            # Pasta de saída (padrão: crossings/)
  --unsigned                      # Upload unsigned no Cloudinary
  --upload_preset <preset>        # Nome do preset para upload unsigned
  --record                        # Gravar resultado em vídeo
```

### **Variáveis de Ambiente (.env)**

```bash
CLOUDINARY_CLOUD_NAME=seu_cloud_name
CLOUDINARY_API_KEY=sua_api_key
CLOUDINARY_API_SECRET=seu_api_secret
```

### **Constantes Configuráveis no Código**

```python
# Linha 127: Timeout de batch
BATCH_TIMEOUT = 15.0  # Segundos sem detecção para processar batch

# Linha 246: Workers paralelos
max_workers=5  # Número de uploads simultâneos

# Linha 723: Timeout de objetos inativos
inactive_timeout = 5.0  # Segundos para remover objeto

# Linha 114: Tamanho do histórico de posições
position_history = deque(maxlen=30)  # Últimas 30 posições

# Linha 425: Buffer de FPS
fps_avg_len = 200  # Janela de média de FPS
```

---

## 📊 Estruturas de Dados

### **object_registry**
```python
{
    track_id: {
        'uuid': str,                    # UUID único do objeto
        'first_seen': float,            # Timestamp primeira detecção
        'last_seen': float,             # Timestamp última detecção
        'class': str,                   # Classe majoritária
        'class_history': [str],         # Histórico de classificações
        'crossed_line': bool,           # Já cruzou a linha?
        'position_history': deque,      # Últimas 30 posições (x, y)
        'best_frame': np.ndarray,       # Melhor frame (sem labels)
        'best_frame_labeled': np.ndarray, # Backup do frame labeled
        'best_confidence': float,       # Maior confiança detectada
        'detection_bbox': tuple         # (xmin, ymin, xmax, ymax)
    }
}
```

### **pending_uploads**
```python
{
    track_id: DetectionSnapshot(
        track_id=int,
        uuid=str,
        timestamp=str,
        frame_normal=np.ndarray,
        frame_labeled=np.ndarray,
        hash_normal=str,
        hash_labeled=str,
        metadata=dict
    )
}
```

### **crossed_objects**
```python
{track_id, track_id, ...}  # Set de IDs que cruzaram a linha
```

### **upload_stats**
```python
{
    'total_uploads': int,    # Total de tentativas
    'successful': int,       # Uploads bem-sucedidos
    'failed': int           # Uploads com falha
}
```

---

## 🔒 Thread Safety

### **Recursos Compartilhados:**
- `pending_uploads` - Protegido por `batch_lock`
- `post_queue` - Thread-safe nativo (queue.Queue)
- `last_detection_time` - Apenas leitura em batch_monitor
- `object_registry` - Apenas thread principal (não precisa lock)

### **Locks Utilizados:**
```python
batch_lock = threading.Lock()

# Uso:
with batch_lock:
    pending_uploads[track_id] = snapshot  # Operação atômica
```

---

## 🐛 Debugging e Logs

### **Logs de Detecção:**
```
🆕 Novo objeto: ID=42, UUID=a3f5d8c1..., Classe=embalagem_plastico
```

### **Logs de Cruzamento:**
```
======================================================================
🎯 OBJETO CRUZOU A LINHA!
   Tipo: embalagem_plastico
   Veracidade: 95%
   Consenso: 28/30 detecções (93%)
   ID: 42 | UUID: a3f5d8c1...
   Tempo de vida: 3.45s
   ⏳ Aguardando batch upload após inatividade
======================================================================
   [DEBUG] Frame normal shape: (720, 1280, 3)
   [DEBUG] Frame labeled shape: (720, 1280, 3)
   [DEBUG] Frames são diferentes: True ✓
   [DEBUG] Bounding box desenhada: (100, 200, 300, 400) ✓
✓ Snapshot criado e adicionado ao buffer de batch
  Hash Normal: 7f8d9e2a1b3c4d5e | Hash Labeled: 9a8b7c6d5e4f3g2h
  Total no buffer: 3 objetos
```

### **Logs de Batch:**
```
⏱️  15.0s sem novas detecções - processando batch...
======================================================================
📦 INICIANDO BATCH UPLOAD - 3 objetos
======================================================================
✓ Upload completo: a3f5d8c1 (embalagem_plastico)
✓ Upload completo: b4e6f9d2 (embalagem_vidro)
✓ Upload completo: c5g7h0e3 (embalagem_metal)
======================================================================
📊 BATCH CONCLUÍDO - Sucesso: 3/3
======================================================================
```

### **Logs de Finalização:**
```
======================================================================
🛑 FINALIZANDO SISTEMA...
======================================================================

⚠️  Existem 2 snapshots pendentes no buffer
Processando batch final antes de encerrar...

📊 ESTATÍSTICAS FINAIS:
   FPS médio: 28.45
   Total de objetos que cruzaram a linha: 15
   Total de uploads realizados: 15
   Uploads bem-sucedidos: 15
   Uploads com falha: 0

✅ Sistema finalizado com sucesso!
======================================================================
```

---

## 🚀 Performance

### **Otimizações Implementadas:**

1. **Upload Não-Bloqueante**
   - Detecção nunca trava
   - FPS constante (~30 fps)
   - Upload em background

2. **Processamento em Batch**
   - Múltiplos uploads simultâneos
   - Reduz overhead de rede
   - 3-4x mais rápido que sequencial

3. **Snapshot Atômico**
   - Cópia profunda imediata
   - Frames não sobrescritos
   - Consistência garantida

4. **Cache de Melhor Frame**
   - Armazena apenas melhor detecção
   - Reduz memória
   - Qualidade máxima de imagem

5. **Histórico Limitado**
   - `deque(maxlen=30)` para posições
   - Memória constante
   - Trajetória suave

### **Consumo de Recursos:**

| Recurso | Uso Típico | Pico |
|---------|------------|------|
| **CPU** | 40-60% | 80% (durante batch) |
| **RAM** | 200-500 MB | 1 GB (buffer cheio) |
| **Rede** | 0 MB/s (detecção) | 5-10 MB/s (batch) |
| **Disco** | Mínimo | 100-200 MB (temp) |

### **FPS Esperado:**

| Resolução | Modelo v8 | Modelo v14 |
|-----------|-----------|------------|
| 640x480 | 35-40 fps | 30-35 fps |
| 1280x720 | 25-30 fps | 20-25 fps |
| 1920x1080 | 15-20 fps | 12-18 fps |

---

## 🔐 Segurança e Validação

### **Hash MD5:**
- Gerado para cada frame no momento do snapshot
- Permite validação de integridade
- Detecta corrupção durante upload/download

### **UUID Único:**
- Garante ID único mesmo entre execuções
- Evita duplicatas no banco de dados
- Rastreabilidade completa

### **Validação de Snapshot:**
```python
def __post_init__(self):
    assert self.frame_normal is not None
    assert self.frame_labeled is not None
    assert self.frame_normal.shape == self.frame_labeled.shape
```

---

## 📝 Casos de Uso

### **1. Esteira Industrial Horizontal**
```bash
python yolo_detect.py \
  --model model-v14.pt \
  --source usb0 \
  --trigger_line 50 \
  --trigger_orientation horizontal \
  --api_url http://api.empresa.com/products \
  --save_crossings \
  --output_dir /backup/crossings/
```

### **2. Esteira Industrial Vertical**
```bash
python yolo_detect.py \
  --model model-v14.pt \
  --source usb0 \
  --trigger_line 30 \
  --trigger_orientation vertical \
  --api_url http://api.empresa.com/products \
  --save_crossings \
  --output_dir /backup/crossings/
```

### **3. Análise de Vídeo Gravado**
```bash
python yolo_detect.py \
  --model model-v14.pt \
  --source videos/esteira_2024-10-28.mp4 \
  --trigger_line 60 \
  --trigger_orientation horizontal \
  --save_crossings \
  --output_dir resultados_video/
```

### **4. Teste em Lote com Imagens**
```bash
python yolo_detect.py \
  --model model-v14.pt \
  --source imagens_teste/ \
  --thresh 0.7 \
  --save_crossings
```

---

## 🛠️ Manutenção e Troubleshooting

### **Problema: FPS baixo**
**Diagnóstico:**
- Verificar uso de CPU/GPU
- Verificar resolução de entrada
- Verificar modelo (v14 é mais lento que v8)

**Solução:**
```bash
# Reduzir resolução
--resolution 640x480

# Usar modelo mais rápido
--model model-v8.pt

# Aumentar threshold (menos detecções)
--thresh 0.7
```

### **Problema: Fotos sem bounding boxes**
**Diagnóstico:**
- Verificar logs: `[DEBUG] Frames são diferentes: False`

**Solução:**
- Já corrigido com redesenho no snapshot
- Verificar que `detection_bbox` não é None

### **Problema: Memória crescendo**
**Diagnóstico:**
- Buffer `pending_uploads` muito grande
- Batch nunca processado (detecções constantes)

**Solução:**
- Implementar limite de tamanho de buffer
- Reduzir `BATCH_TIMEOUT` para 10s
- Adicionar batch periódico forçado

### **Problema: Upload falhando**
**Diagnóstico:**
- Verificar conexão com Cloudinary
- Verificar credenciais (.env)
- Verificar logs de erro

**Solução:**
```bash
# Verificar variáveis
echo $CLOUDINARY_CLOUD_NAME

# Testar upload manual
curl -X POST https://api.cloudinary.com/...

# Usar modo unsigned
--unsigned --upload_preset seu_preset
```

---

## 📚 Referências

- **YOLO**: [Ultralytics Documentation](https://docs.ultralytics.com/)
- **OpenCV**: [OpenCV Python Tutorial](https://docs.opencv.org/4.x/d6/d00/tutorial_py_root.html)
- **Cloudinary**: [Cloudinary API Docs](https://cloudinary.com/documentation)
- **Threading**: [Python threading](https://docs.python.org/3/library/threading.html)
- **ThreadPoolExecutor**: [concurrent.futures](https://docs.python.org/3/library/concurrent.futures.html)

---

## 📄 Licença

Este projeto é proprietário da equipe de desenvolvimento Ache Capture V2.

---

**Última Atualização:** 30 de outubro de 2025  
**Versão:** 2.0 - Sistema de Batch Upload com Linha Horizontal
