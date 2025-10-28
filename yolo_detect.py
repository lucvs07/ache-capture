from dotenv import load_dotenv
import cloudinary
import cloudinary.uploader
from cloudinary.utils import cloudinary_url
import os
import sys
import argparse
import glob
import time
import random
import cv2
import numpy as np
from ultralytics import YOLO
import datetime
import requests
import threading
import queue
import uuid
import hashlib
from collections import defaultdict, deque, Counter
from concurrent.futures import ThreadPoolExecutor, wait
from dataclasses import dataclass
from typing import Dict, Optional

load_dotenv()

# ============================================================================
# DATACLASS: Snapshot Imutável para Garantir Consistência de Fotos
# ============================================================================
@dataclass
class DetectionSnapshot:
    """
    Estrutura imutável que garante que as fotos normal e labeled
    são do mesmo frame exato, evitando inconsistências.
    """
    track_id: int
    uuid: str
    timestamp: str
    frame_normal: np.ndarray  # Frame sem labels
    frame_labeled: np.ndarray  # Frame com labels
    hash_normal: str  # MD5 para validação
    hash_labeled: str  # MD5 para validação
    metadata: Dict  # Dados para API (tipo, confiança, etc)
    
    def __post_init__(self):
        """Validação após criação"""
        assert self.frame_normal is not None, "Frame normal não pode ser None"
        assert self.frame_labeled is not None, "Frame labeled não pode ser None"
        assert self.frame_normal.shape == self.frame_labeled.shape, "Frames devem ter mesma dimensão"

# Configuration       
cloudinary.config( 
    cloud_name = os.getenv("CLOUDINARY_CLOUD_NAME"), 
    api_key = os.getenv("CLOUDINARY_API_KEY"), 
    api_secret = os.getenv("CLOUDINARY_API_SECRET"),
    secure=True
)

# Validate Cloudinary configuration if using signed uploads, or check preset for unsigned
_cloud = os.getenv("CLOUDINARY_CLOUD_NAME")
_key = os.getenv("CLOUDINARY_API_KEY")
_secret = os.getenv("CLOUDINARY_API_SECRET")

# args isn't parsed yet here, so only do a basic env check for signed uploads
if (not _cloud) or (not _key) or (not _secret):
    print('Warning: Cloudinary environment variables may be missing. If you plan to use signed uploads, set CLOUDINARY_CLOUD_NAME, CLOUDINARY_API_KEY, and CLOUDINARY_API_SECRET in your .env file.')

# Define and parse user input arguments

parser = argparse.ArgumentParser()
parser.add_argument('--model', help='Path to YOLO model file (example: "runs/detect/train/weights/best.pt")',
                    required=True)
parser.add_argument('--source', help='Image source, can be image file ("test.jpg"), \
                    image folder ("test_dir"), video file ("testvid.mp4"), index of USB camera ("usb0"), or index of Picamera ("picamera0")', 
                    required=True)
parser.add_argument('--thresh', help='Minimum confidence threshold for displaying detected objects (example: "0.4")',
                    default=0.5)
parser.add_argument('--resolution', help='Resolution in WxH to display inference results at (example: "640x480"), \
                    otherwise, match source resolution',
                    default=None)
parser.add_argument('--record', help='Record results from video or webcam and save it as "demo1.avi". Must specify --resolution argument to record.',
                    action='store_true')
parser.add_argument('--unsigned', help='Use unsigned upload (requires --upload_preset configured in Cloudinary)', action='store_true')
parser.add_argument('--upload_preset', help='Upload preset name to use with unsigned uploads', default=None)
parser.add_argument('--api_url', help='HTTP API URL to POST Product JSON to (example: http://localhost:3000/api/products)', default=None)
parser.add_argument('--api_timeout', help='Timeout (seconds) for API POST requests. Use 0 for no timeout.', type=float, default=10.0)
parser.add_argument('--trigger_line', help='X-coordinate for trigger line as percentage of frame width (0-100, example: "50" for center)', 
                    type=int, default=50)
parser.add_argument('--save_crossings', help='Save images of objects that cross the trigger line locally', action='store_true')
parser.add_argument('--output_dir', help='Directory to save crossing images (default: "crossings")', default='crossings')

args = parser.parse_args()


# Parse user inputs
model_path = args.model
img_source = args.source
min_thresh = float(args.thresh)
user_res = args.resolution
record = args.record

# Check if model file exists and is valid
if (not os.path.exists(model_path)):
    print('ERROR: Model path is invalid or model was not found. Make sure the model filename was entered correctly.')
    sys.exit(0)

# Load the model into memory and get labemap
model = YOLO(model_path, task='detect')
labels = model.names

# Tracking data structures
track_history = defaultdict(lambda: deque(maxlen=30))
object_registry = {}  # {track_id: {'uuid', 'first_seen', 'class', 'crossed_line', 'best_frame', 'best_frame_labeled', 'best_confidence'}}
crossed_objects = set()

# ============================================================================
# SISTEMA DE BATCH UPLOAD: Processa uploads após período de inatividade
# ============================================================================
pending_uploads = {}  # Buffer de snapshots aguardando upload
last_detection_time = None  # Timestamp da última detecção
BATCH_TIMEOUT = 15.0  # Segundos de inatividade antes de processar batch
batch_lock = threading.Lock()  # Lock para acesso thread-safe ao buffer
batch_processing = False  # Flag para evitar processamento simultâneo
upload_stats = {'total_uploads': 0, 'successful': 0, 'failed': 0}  # Estatísticas

# Create output directory for saving crossings if needed
if args.save_crossings or not args.api_url:
    os.makedirs(args.output_dir, exist_ok=True)
    if args.save_crossings:
        print(f'Salvando imagens de cruzamentos em: {args.output_dir}/')
    elif not args.api_url:
        print(f'API não configurada. Salvando imagens localmente em: {args.output_dir}/')

# Background poster: use a queue and a worker thread to POST Product JSONs without
# blocking the capture loop. Each queue entry is a dict with keys: url, json, headers, timeout
post_queue = queue.Queue()

# ============================================================================
# FUNÇÕES DE UPLOAD E PROCESSAMENTO EM BATCH
# ============================================================================

def upload_snapshot_to_cloudinary(snapshot: DetectionSnapshot) -> Optional[Dict]:
    """
    Faz upload de um snapshot (normal + labeled) para o Cloudinary.
    Retorna dicionário com URLs ou None em caso de erro.
    """
    try:
        timestamp = snapshot.timestamp
        obj_uuid = snapshot.uuid
        obj_class = snapshot.metadata.get('tipo', 'unknown')
        
        # Criar nomes de arquivo com hash para garantir unicidade
        filename_sem = f'analysis_{obj_uuid[:8]}_{timestamp}_{obj_class}_normal.jpg'
        filename_com = f'analysis_{obj_uuid[:8]}_{timestamp}_{obj_class}_labeled.jpg'
        
        # Salvar temporariamente (necessário para upload)
        temp_path_sem = os.path.join(os.getcwd(), filename_sem)
        temp_path_com = os.path.join(os.getcwd(), filename_com)
        
        cv2.imwrite(temp_path_sem, snapshot.frame_normal)
        cv2.imwrite(temp_path_com, snapshot.frame_labeled)
        
        # Upload para Cloudinary
        if args.unsigned:
            if not args.upload_preset:
                print(f'❌ Erro: --upload_preset necessário para upload unsigned')
                return None
            resp_sem = cloudinary.uploader.unsigned_upload(
                temp_path_sem, args.upload_preset, folder='ache-capture/normal')
            resp_com = cloudinary.uploader.unsigned_upload(
                temp_path_com, args.upload_preset, folder='ache-capture/labeled')
        else:
            resp_sem = cloudinary.uploader.upload(temp_path_sem, folder='ache-capture/normal')
            resp_com = cloudinary.uploader.upload(temp_path_com, folder='ache-capture/labeled')
        
        # Limpar arquivos temporários
        os.remove(temp_path_sem)
        os.remove(temp_path_com)
        
        return {
            'url_normal': resp_sem.get('secure_url'),
            'url_labeled': resp_com.get('secure_url'),
            'hash_normal': snapshot.hash_normal,
            'hash_labeled': snapshot.hash_labeled
        }
        
    except Exception as e:
        print(f'❌ Erro no upload do snapshot {snapshot.uuid[:8]}: {e}')
        return None


def send_to_api(snapshot: DetectionSnapshot, cloudinary_urls: Dict) -> bool:
    """
    Envia dados do snapshot para a API configurada.
    Retorna True se sucesso, False se falha.
    """
    try:
        product = {
            'id': snapshot.uuid,  # Usar UUID como ID único (evita duplicatas)
            'trackId': snapshot.track_id,  # Manter track_id como informação adicional
            'uuid': snapshot.uuid,
            'data': datetime.datetime.now().isoformat(),
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
        
        # Enviar via queue do post_worker (já existente)
        post_timeout = None if (args.api_timeout <= 0) else args.api_timeout
        post_queue.put({
            'url': args.api_url,
            'json': product,
            'headers': {'Content-Type': 'application/json'},
            'timeout': post_timeout
        })
        
        return True
        
    except Exception as e:
        print(f'❌ Erro ao enviar para API: {e}')
        return False


def process_batch_uploads():
    """
    Processa todos os snapshots pendentes em batch.
    Executado após período de inatividade.
    """
    global batch_processing, upload_stats
    
    with batch_lock:
        if batch_processing or len(pending_uploads) == 0:
            return
        
        batch_processing = True
        snapshots_to_process = list(pending_uploads.values())
        pending_uploads.clear()
    
    print('\n' + '=' * 70)
    print(f'📦 INICIANDO BATCH UPLOAD - {len(snapshots_to_process)} objetos')
    print('=' * 70)
    
    # Upload paralelo para Cloudinary
    with ThreadPoolExecutor(max_workers=5) as executor:
        upload_futures = {
            executor.submit(upload_snapshot_to_cloudinary, snap): snap 
            for snap in snapshots_to_process
        }
        
        # Aguardar todos os uploads
        for future in upload_futures:
            snapshot = upload_futures[future]
            upload_stats['total_uploads'] += 1
            
            try:
                result = future.result(timeout=30)
                if result and args.api_url:
                    # Enviar para API
                    if send_to_api(snapshot, result):
                        upload_stats['successful'] += 1
                        print(f'✓ Upload completo: {snapshot.uuid[:8]} ({snapshot.metadata["tipo"]})')
                    else:
                        upload_stats['failed'] += 1
                elif result:
                    upload_stats['successful'] += 1
                    print(f'✓ Imagens salvas: {snapshot.uuid[:8]} ({snapshot.metadata["tipo"]})')
                else:
                    upload_stats['failed'] += 1
            except Exception as e:
                upload_stats['failed'] += 1
                print(f'✗ Falha no upload: {snapshot.uuid[:8]} - {e}')
    
    print('=' * 70)
    print(f'📊 BATCH CONCLUÍDO - Sucesso: {upload_stats["successful"]}/{upload_stats["total_uploads"]}')
    print('=' * 70 + '\n')
    
    batch_processing = False


def batch_monitor_worker():
    """
    Thread que monitora inatividade e dispara batch upload.
    Roda em background durante toda a execução.
    """
    global last_detection_time
    
    while True:
        time.sleep(1)  # Verifica a cada 1 segundo
        
        if last_detection_time is None:
            continue
        
        # Verificar se passou tempo suficiente sem detecções
        idle_time = time.time() - last_detection_time
        
        if idle_time >= BATCH_TIMEOUT and len(pending_uploads) > 0:
            print(f'\n⏱️  {BATCH_TIMEOUT}s sem novas detecções - processando batch...')
            process_batch_uploads()
            last_detection_time = None  # Reset timer

def post_worker(q: queue.Queue):
    session = requests.Session()
    while True:
        item = q.get()
        try:
            if item is None:
                break
            url = item.get('url')
            payload = item.get('json')
            headers = item.get('headers')
            timeout = item.get('timeout')
            try:
                r = session.post(url, json=payload, headers=headers, timeout=timeout)
                if r.status_code >= 200 and r.status_code < 300:
                    print(f'✓ POST enviado com sucesso: {payload.get("uuid", "N/A")}')
                else:
                    print(f'✗ POST falhou: {r.status_code} - {r.text}')
            except Exception as e:
                print(f'✗ Erro no POST: {e}')
        finally:
            q.task_done()

# Start background poster thread (daemon so it doesn't block process exit if something goes wrong)
post_thread = threading.Thread(target=post_worker, args=(post_queue,), daemon=True)
post_thread.start()

# Start batch monitor thread
batch_thread = threading.Thread(target=batch_monitor_worker, daemon=True)
batch_thread.start()
print('🚀 Sistema de batch upload iniciado (timeout: 15s)')

# Parse input to determine if image source is a file, folder, video, or USB camera
img_ext_list = ['.jpg','.JPG','.jpeg','.JPEG','.png','.PNG','.bmp','.BMP']
vid_ext_list = ['.avi','.mov','.mp4','.mkv','.wmv']

if os.path.isdir(img_source):
    source_type = 'folder'
elif os.path.isfile(img_source):
    _, ext = os.path.splitext(img_source)
    if ext in img_ext_list:
        source_type = 'image'
    elif ext in vid_ext_list:
        source_type = 'video'
    else:
        print(f'File extension {ext} is not supported.')
        sys.exit(0)
elif 'usb' in img_source:
    source_type = 'usb'
    usb_idx = int(img_source[3:])
elif 'picamera' in img_source:
    source_type = 'picamera'
    picam_idx = int(img_source[8:])
else:
    print(f'Input {img_source} is invalid. Please try again.')
    sys.exit(0)

# Parse user-specified display resolution
resize = False
if user_res:
    resize = True
    resW, resH = int(user_res.split('x')[0]), int(user_res.split('x')[1])

# Check if recording is valid and set up recording
if record:
    if source_type not in ['video','usb']:
        print('Recording only works for video and camera sources. Please try again.')
        sys.exit(0)
    if not user_res:
        print('Please specify resolution to record video at.')
        sys.exit(0)
    
    # Set up recording
    record_name = 'demo1.avi'
    record_fps = 30
    recorder = cv2.VideoWriter(record_name, cv2.VideoWriter_fourcc(*'MJPG'), record_fps, (resW,resH))

# Load or initialize image source
if source_type == 'image':
    imgs_list = [img_source]
elif source_type == 'folder':
    imgs_list = []
    filelist = glob.glob(img_source + '/*')
    for file in filelist:
        _, file_ext = os.path.splitext(file)
        if file_ext in img_ext_list:
            imgs_list.append(file)
elif source_type == 'video' or source_type == 'usb':

    if source_type == 'video': cap_arg = img_source
    elif source_type == 'usb': cap_arg = usb_idx
    cap = cv2.VideoCapture(cap_arg)

    # Set camera or video resolution if specified by user
    if user_res:
        ret = cap.set(3, resW)
        ret = cap.set(4, resH)

elif source_type == 'picamera':
    from picamera2 import Picamera2
    cap = Picamera2()
    cap.configure(cap.create_video_configuration(main={"format": 'RGB888', "size": (resW, resH)}))
    cap.start()

# Set bounding box colors (using the Tableu 10 color scheme)
bbox_colors = [(164,120,87), (68,148,228), (93,97,209), (178,182,133), (88,159,106), 
              (96,202,231), (159,124,168), (169,162,241), (98,118,150), (172,176,184)]

# Initialize control and status variables
avg_frame_rate = 0
frame_rate_buffer = []
fps_avg_len = 200
img_count = 0

print('=' * 60)
print('Sistema de Rastreamento e Análise de Embalagens')
print('=' * 60)
print(f'Fonte: {img_source}')
print(f'Tipo: {source_type}')
print(f'Modelo: {model_path}')
print(f'Trigger Line: {args.trigger_line}% da largura (linha vertical)')
print(f'API URL: {args.api_url if args.api_url else "Não configurada"}')
print(f'Salvar cruzamentos: {"Sim" if args.save_crossings else "Não"}')
if args.save_crossings:
    print(f'Pasta de saída: {args.output_dir}/')
print('=' * 60)

# Begin inference loop
while True:

    t_start = time.perf_counter()

    # Load frame from image source
    if source_type == 'image' or source_type == 'folder': # If source is image or image folder, load the image using its filename
        if img_count >= len(imgs_list):
            print('All images have been processed. Exiting program.')
            sys.exit(0)
        img_filename = imgs_list[img_count]
        frame = cv2.imread(img_filename)
        img_count = img_count + 1
    
    elif source_type == 'video': # If source is a video, load next frame from video file
        ret, frame = cap.read()
        if not ret:
            print('Reached end of the video file. Exiting program.')
            break
    
    elif source_type == 'usb': # If source is a USB camera, grab frame from camera
        ret, frame = cap.read()
        if (frame is None) or (not ret):
            print('Unable to read frames from the camera. This indicates the camera is disconnected or not working. Exiting program.')
            break

    elif source_type == 'picamera': # If source is a Picamera, grab frames using picamera interface
        frame = cap.capture_array()
        if (frame is None):
            print('Unable to read frames from the Picamera. This indicates the camera is disconnected or not working. Exiting program.')
            break

    # Resize frame to desired display resolution
    if resize == True:
        frame = cv2.resize(frame,(resW,resH))

    # Calculate trigger line position (vertical line at X)
    trigger_x = int((args.trigger_line / 100) * frame.shape[1])

    # Save clean frame copy
    frame_sem_label = frame.copy()

    # Run tracking inference
    results = model.track(frame, persist=True, verbose=False)

    # Extract results
    detections = results[0].boxes

    current_time = time.time()
    active_tracks = set()

    # Go through each detection and get bbox coords, confidence, and class
    for i in range(len(detections)):

        # Get bounding box coordinates
        # Ultralytics returns results in Tensor format, which have to be converted to a regular Python array
        xyxy_tensor = detections[i].xyxy.cpu() # Detections in Tensor format in CPU memory
        xyxy = xyxy_tensor.numpy().squeeze() # Convert tensors to Numpy array
        xmin, ymin, xmax, ymax = xyxy.astype(int) # Extract individual coordinates and convert to int

        # Get bounding box class ID and name
        classidx = int(detections[i].cls.item())
        classname = labels[classidx]

        # Get bounding box confidence
        conf = detections[i].conf.item()

        # Get track ID if available
        if detections[i].id is not None and conf > min_thresh:
            track_id = int(detections[i].id.item())
            active_tracks.add(track_id)
            
            # Atualizar timer de última detecção para sistema de batch
            last_detection_time = time.time()
            
            # Calculate center
            center_x = int((xmin + xmax) / 2)
            center_y = int((ymin + ymax) / 2)
            
            # Register new object
            if track_id not in object_registry:
                object_uuid = str(uuid.uuid4())
                object_registry[track_id] = {
                    'uuid': object_uuid,
                    'first_seen': current_time,
                    'last_seen': current_time,
                    'class': classname,
                    'class_history': [],  # Histórico de todas as classes detectadas
                    'crossed_line': False,
                    'position_history': deque(maxlen=30),
                    'best_frame': None,
                    'best_frame_labeled': None,
                    'best_confidence': 0.0,
                    'detection_bbox': None
                }
                print(f'🆕 Novo objeto: ID={track_id}, UUID={object_uuid[:8]}..., Classe={classname}')
            
            # Update last seen and position
            object_registry[track_id]['last_seen'] = current_time
            object_registry[track_id]['position_history'].append((center_x, center_y))
            
            # Add current class to history
            object_registry[track_id]['class_history'].append(classname)
            
            # Calculate most frequent class (majority vote)
            class_counter = Counter(object_registry[track_id]['class_history'])
            most_common_class = class_counter.most_common(1)[0][0]
            object_registry[track_id]['class'] = most_common_class
            
            # Store best frame (highest confidence) - SNAPSHOT ATÔMICO
            if conf > object_registry[track_id]['best_confidence']:
                object_registry[track_id]['best_confidence'] = conf
                # Armazenar apenas o frame limpo (sem labels)
                # O frame labeled será gerado no momento do cruzamento com as boxes corretas
                object_registry[track_id]['best_frame'] = frame_sem_label.copy()
                object_registry[track_id]['best_frame_labeled'] = frame.copy()  # Backup (não usado no snapshot)
                object_registry[track_id]['detection_bbox'] = (xmin, ymin, xmax, ymax)
            
            # Check trigger line crossing (use X coordinate for vertical line)
            if len(object_registry[track_id]['position_history']) >= 2:
                prev_x = object_registry[track_id]['position_history'][-2][0]
                curr_x = center_x
                
                # Detect crossing (left to right or right to left)
                if (prev_x < trigger_x <= curr_x) or (prev_x > trigger_x >= curr_x):
                    if not object_registry[track_id]['crossed_line']:
                        object_registry[track_id]['crossed_line'] = True
                        crossed_objects.add(track_id)
                        
                        lifetime = current_time - object_registry[track_id]['first_seen']
                        obj_uuid = object_registry[track_id]['uuid']
                        best_conf = object_registry[track_id]['best_confidence']
                        majority_class = object_registry[track_id]['class']  # Usar classe majoritária
                        
                        # Calcular estatísticas da votação
                        class_counter = Counter(object_registry[track_id]['class_history'])
                        vote_count = class_counter[majority_class]
                        total_votes = len(object_registry[track_id]['class_history'])
                        vote_percent = int((vote_count / total_votes) * 100) if total_votes > 0 else 0
                        
                        # Print tipo e veracidade imediatamente (com classe majoritária)
                        print('=' * 70)
                        print(f'🎯 OBJETO CRUZOU A LINHA!')
                        print(f'   Tipo: {majority_class}')
                        print(f'   Veracidade: {int(best_conf * 100)}%')
                        print(f'   Consenso: {vote_count}/{total_votes} detecções ({vote_percent}%)')
                        print(f'   ID: {track_id} | UUID: {obj_uuid[:8]}...')
                        print(f'   Tempo de vida: {lifetime:.2f}s')
                        print(f'   ⏳ Aguardando batch upload após inatividade')
                        print('=' * 70)
                        
                        # ============================================================
                        # CRIAR SNAPSHOT ATÔMICO E ADICIONAR AO BUFFER DE BATCH
                        # ============================================================
                        try:
                            timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
                            
                            # CORREÇÃO CRÍTICA: Capturar o frame atual que TEM as boxes desenhadas
                            # O best_frame_labeled foi atualizado no passado, mas queremos o frame ATUAL
                            # que está sendo processado neste momento (com todas as boxes atuais)
                            
                            # Frame normal: usar o melhor frame sem labels (correto)
                            snapshot_normal = object_registry[track_id]['best_frame'].copy()
                            
                            # Frame labeled: precisamos redesenhar as boxes no melhor frame
                            # para garantir que tenha as bounding boxes
                            snapshot_labeled = object_registry[track_id]['best_frame'].copy()  # Começa com frame limpo
                            
                            # Redesenhar bounding box no frame labeled
                            bbox = object_registry[track_id]['detection_bbox']
                            if bbox:
                                xmin_snap, ymin_snap, xmax_snap, ymax_snap = bbox
                                color = bbox_colors[classidx % 10]
                                
                                # Desenhar retângulo
                                cv2.rectangle(snapshot_labeled, (xmin_snap, ymin_snap), (xmax_snap, ymax_snap), color, 2)
                                
                                # Desenhar label
                                label = f'{majority_class}: {int(best_conf*100)}%'
                                labelSize, baseLine = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
                                label_ymin = max(ymin_snap, labelSize[1] + 10)
                                cv2.rectangle(snapshot_labeled, (xmin_snap, label_ymin-labelSize[1]-10), 
                                            (xmin_snap+labelSize[0], label_ymin+baseLine-10), color, cv2.FILLED)
                                cv2.putText(snapshot_labeled, label, (xmin_snap, label_ymin-7), 
                                          cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 1)
                                
                                # Adicionar info de tracking
                                info_text = f'ID:{track_id} | {lifetime:.1f}s | {vote_count}/{total_votes} ({vote_percent}%)'
                                cv2.putText(snapshot_labeled, info_text, (xmin_snap, ymin_snap - 25), 
                                          cv2.FONT_HERSHEY_SIMPLEX, 0.4, color, 1)
                            
                            # [DEBUG] Logs de diagnóstico
                            print(f'   [DEBUG] Frame normal shape: {snapshot_normal.shape}')
                            print(f'   [DEBUG] Frame labeled shape: {snapshot_labeled.shape}')
                            frames_different = not np.array_equal(snapshot_normal, snapshot_labeled)
                            print(f'   [DEBUG] Frames são diferentes: {frames_different} {"✓" if frames_different else "⚠️"}')
                            if bbox:
                                print(f'   [DEBUG] Bounding box desenhada: {bbox} ✓')
                            
                            # Gerar hashes MD5 para validação
                            hash_normal = hashlib.md5(snapshot_normal.tobytes()).hexdigest()[:16]
                            hash_labeled = hashlib.md5(snapshot_labeled.tobytes()).hexdigest()[:16]
                            
                            # Criar estrutura de metadados
                            metadata = {
                                'tipo': majority_class,
                                'aprovado': best_conf > 0.7,
                                'status': 'aprovado' if best_conf > 0.7 else 'verificar',
                                'veracidade': f"{int(best_conf * 100)}%",
                                'confianca': best_conf,
                                'consenso': f"{vote_count}/{total_votes}",
                                'consensoPercentual': vote_percent,
                                'tempoVidaSegundos': round(lifetime, 2)
                            }
                            
                            # Criar snapshot imutável
                            snapshot = DetectionSnapshot(
                                track_id=track_id,
                                uuid=obj_uuid,
                                timestamp=timestamp,
                                frame_normal=snapshot_normal,
                                frame_labeled=snapshot_labeled,
                                hash_normal=hash_normal,
                                hash_labeled=hash_labeled,
                                metadata=metadata
                            )
                            
                            # Adicionar ao buffer de batch (thread-safe)
                            with batch_lock:
                                pending_uploads[track_id] = snapshot
                            
                            print(f'✓ Snapshot criado e adicionado ao buffer de batch')
                            print(f'  Hash Normal: {hash_normal} | Hash Labeled: {hash_labeled}')
                            print(f'  Total no buffer: {len(pending_uploads)} objetos')
                            
                            # Salvar localmente SE --save_crossings estiver ativo
                            if args.save_crossings:
                                filename_sem = f'crossing_{obj_uuid[:8]}_{timestamp}_{majority_class}_normal.jpg'
                                filename_com = f'crossing_{obj_uuid[:8]}_{timestamp}_{majority_class}_labeled.jpg'
                                path_sem = os.path.join(args.output_dir, filename_sem)
                                path_com = os.path.join(args.output_dir, filename_com)
                                cv2.imwrite(path_sem, snapshot_normal)
                                cv2.imwrite(path_com, snapshot_labeled)
                                print(f'💾 Cópias salvas localmente em: {args.output_dir}/')
                                    
                        except Exception as e:
                            print(f'❌ Erro ao criar snapshot: {e}')
            
            # Draw bbox and info (use majority class)
            majority_class = object_registry[track_id]['class']
            color = bbox_colors[classidx % 10]
            cv2.rectangle(frame, (xmin,ymin), (xmax,ymax), color, 2)

            label = f'{majority_class}: {int(conf*100)}%'
            labelSize, baseLine = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1) # Get font size
            label_ymin = max(ymin, labelSize[1] + 10) # Make sure not to draw label too close to top of window
            cv2.rectangle(frame, (xmin, label_ymin-labelSize[1]-10), (xmin+labelSize[0], label_ymin+baseLine-10), color, cv2.FILLED) # Draw white box to put label text in
            cv2.putText(frame, label, (xmin, label_ymin-7), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 1) # Draw label text
            
            # Draw tracking info with class vote count
            lifetime = current_time - object_registry[track_id]['first_seen']
            class_counter = Counter(object_registry[track_id]['class_history'])
            vote_count = class_counter[majority_class]
            total_votes = len(object_registry[track_id]['class_history'])
            vote_percent = int((vote_count / total_votes) * 100) if total_votes > 0 else 0
            
            info_text = f'ID:{track_id} | {lifetime:.1f}s | {vote_count}/{total_votes} ({vote_percent}%)'
            cv2.putText(frame, info_text, (xmin, ymin - 25), cv2.FONT_HERSHEY_SIMPLEX, 0.4, color, 1)
            
            # Draw trajectory
            points = list(object_registry[track_id]['position_history'])
            for j in range(1, len(points)):
                cv2.line(frame, points[j-1], points[j], color, 2)

    # Clean up inactive objects
    inactive_timeout = 5.0
    to_remove = []
    for track_id, info in list(object_registry.items()):
        if track_id not in active_tracks:
            if current_time - info['last_seen'] > inactive_timeout:
                to_remove.append(track_id)
                total_lifetime = info['last_seen'] - info['first_seen']
                crossed_status = "✓ CRUZOU" if info['crossed_line'] else "✗ não cruzou"
                print(f'🗑️  Objeto {track_id} removido (timeout). Vida total: {total_lifetime:.2f}s [{crossed_status}]')

    for track_id in to_remove:
        del object_registry[track_id]
        # NÃO remover de crossed_objects - manter contagem de objetos que cruzaram
        # crossed_objects.discard(track_id)  # REMOVIDO para manter contagem correta

    # Draw trigger line (vertical)
    cv2.line(frame, (trigger_x, 0), (trigger_x, frame.shape[0]), (0, 255, 0), 3)
    # Put label near top of the line
    label_x = min(trigger_x + 10, frame.shape[1] - 100)
    cv2.putText(frame, 'TRIGGER LINE', (label_x, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)

    # Calculate and draw framerate (if using video, USB, or Picamera source)
    if source_type in ['video', 'usb', 'picamera']:
        cv2.putText(frame, f'FPS: {avg_frame_rate:0.2f}', (10,25), cv2.FONT_HERSHEY_SIMPLEX, .7, (0,255,255), 2)
    
    # Draw statistics
    cv2.putText(frame, f'Objetos ativos: {len(active_tracks)}', (10, 50), cv2.FONT_HERSHEY_SIMPLEX, .6, (0,255,255), 2)
    cv2.putText(frame, f'Cruzaram linha: {len(crossed_objects)}', (10, 75), cv2.FONT_HERSHEY_SIMPLEX, .6, (0,255,255), 2)

    # Display detection results
    cv2.imshow('Rastreamento de Embalagens - Pressione Q para sair', frame)
    if record: recorder.write(frame)

    # Handle keyboard input
    if source_type in ['image', 'folder']:
        key = cv2.waitKey()
    else:
        key = cv2.waitKey(5)
    
    if key == ord('q') or key == ord('Q'):
        break
    elif key == ord('s') or key == ord('S'):
        cv2.waitKey()
    elif key == ord('p') or key == ord('P'):
        cv2.imwrite('capture.png', frame)
    
    # Calculate FPS
    t_stop = time.perf_counter()
    frame_rate_calc = float(1/(t_stop - t_start))
    
    if len(frame_rate_buffer) >= fps_avg_len:
        frame_rate_buffer.pop(0)
    frame_rate_buffer.append(frame_rate_calc)
    
    avg_frame_rate = np.mean(frame_rate_buffer)

# Cleanup
print('\n' + '=' * 70)
print('🛑 FINALIZANDO SISTEMA...')
print('=' * 70)

# Processar qualquer batch pendente antes de encerrar
if len(pending_uploads) > 0:
    print(f'\n⚠️  Existem {len(pending_uploads)} snapshots pendentes no buffer')
    print('Processando batch final antes de encerrar...')
    process_batch_uploads()

print(f'\n📊 ESTATÍSTICAS FINAIS:')
print(f'   FPS médio: {avg_frame_rate:.2f}')
print(f'   Total de objetos que cruzaram a linha: {len(crossed_objects)}')
print(f'   Total de uploads realizados: {upload_stats["total_uploads"]}')
print(f'   Uploads bem-sucedidos: {upload_stats["successful"]}')
print(f'   Uploads com falha: {upload_stats["failed"]}')

if source_type in ['video', 'usb']:
    cap.release()
elif source_type == 'picamera':
    cap.stop()
if record: 
    recorder.release()
cv2.destroyAllWindows()

# Signal background poster to exit and wait for it to finish
post_queue.put(None)
post_queue.join()

print('\n✅ Sistema finalizado com sucesso!')
print('=' * 70)
