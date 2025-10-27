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
from collections import defaultdict, deque, Counter

load_dotenv()
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
parser.add_argument('--inactive_timeout', help='Timeout for inactive objects in seconds (default: 10.0)', 
                    type=float, default=10.0)
parser.add_argument('--trigger_buffer', help='Buffer zone around trigger line in pixels (default: 50)', 
                    type=int, default=50)
parser.add_argument('--predict_missing', help='Predict position when detection is lost', 
                    action='store_true')

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

def predict_next_position(position_history):
    """Prediz próxima posição baseada na траектória recente"""
    if len(position_history) < 3:
        return None
    
    # Calcular velocidade média dos últimos 3 pontos
    recent_points = list(position_history)[-3:]
    vx = (recent_points[-1][0] - recent_points[0][0]) / 2
    vy = (recent_points[-1][1] - recent_points[0][1]) / 2
    
    # Predizer próxima posição
    next_x = recent_points[-1][0] + vx
    next_y = recent_points[-1][1] + vy
    
    return (int(next_x), int(next_y))

def handle_missing_objects(object_registry, active_tracks, trigger_x, trigger_buffer, 
                          current_time, frame, crossed_objects, args):
    """Gerencia objetos que perderam detecção temporariamente"""
    to_remove = []
    
    for track_id, info in list(object_registry.items()):
        if track_id not in active_tracks:
            time_missing = current_time - info['last_seen']
            
            # 1. Dentro do timeout - tentar predizer ou manter vivo
            if time_missing < args.inactive_timeout:
                
                # Opção: Predição habilitada
                if args.predict_missing and len(info['position_history']) >= 3:
                    predicted_pos = predict_next_position(info['position_history'])
                    
                    if predicted_pos:
                        info['position_history'].append(predicted_pos)
                        
                        # Desenhar predição
                        cv2.circle(frame, predicted_pos, 5, (255, 0, 255), -1)
                        cv2.putText(frame, f'ID:{track_id} (pred)', 
                                   (predicted_pos[0], predicted_pos[1] - 10),
                                   cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 0, 255), 1)
                        
                        # Checar cruzamento com buffer
                        if len(info['position_history']) >= 2:
                            prev_x = info['position_history'][-2][0]
                            curr_x = predicted_pos[0]
                            
                            crossed = False
                            if prev_x < (trigger_x - trigger_buffer) and \
                               curr_x > (trigger_x + trigger_buffer):
                                crossed = True
                            elif prev_x > (trigger_x + trigger_buffer) and \
                                 curr_x < (trigger_x - trigger_buffer):
                                crossed = True
                            
                            if crossed and not info['crossed_line']:
                                info['crossed_line'] = True
                                crossed_objects.add(track_id)
                                
                                # Calcular estatísticas
                                lifetime = current_time - info['first_seen']
                                obj_uuid = info['uuid']
                                best_conf = info['best_confidence']
                                majority_class = info['class']
                                
                                class_counter = Counter(info['class_history'])
                                vote_count = class_counter[majority_class]
                                total_votes = len(info['class_history'])
                                vote_percent = int((vote_count / total_votes) * 100) if total_votes > 0 else 0
                                
                                print('=' * 70)
                                print(f'🎯 OBJETO CRUZOU A LINHA (PREDITO)!')
                                print(f'   Tipo: {majority_class}')
                                print(f'   Veracidade: {int(best_conf * 100)}%')
                                print(f'   Consenso: {vote_count}/{total_votes} detecções ({vote_percent}%)')
                                print(f'   ID: {track_id} | UUID: {obj_uuid[:8]}...')
                                print(f'   Tempo de vida: {lifetime:.2f}s')
                                print('=' * 70)
                                
                                # Marcar para salvar foto
                                info['save_crossing_photo'] = True
                                info['crossing_timestamp'] = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
                
                # Sem predição - apenas manter vivo e mostrar última posição
                else:
                    if info['position_history']:
                        last_pos = info['position_history'][-1]
                        cv2.circle(frame, last_pos, 10, (128, 128, 128), 2)
                        cv2.putText(frame, f'ID:{track_id} (lost {time_missing:.1f}s)', 
                                   (last_pos[0], last_pos[1] - 10),
                                   cv2.FONT_HERSHEY_SIMPLEX, 0.4, (128, 128, 128), 1)
            
            # 2. Timeout excedido - remover
            else:
                to_remove.append(track_id)
                total_lifetime = info['last_seen'] - info['first_seen']
                crossed_status = '[✓ CRUZOU]' if info['crossed_line'] else '[✗ não cruzou]'
                print(f'🗑️  Objeto {track_id} removido (timeout {args.inactive_timeout}s). Vida total: {total_lifetime:.2f}s {crossed_status}')
    
    return to_remove

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
print(f'Buffer Zone: ±{args.trigger_buffer} pixels')
print(f'Timeout Inatividade: {args.inactive_timeout}s')
print(f'Predição de Posição: {"Ativada" if args.predict_missing else "Desativada"}')
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
                    'detection_bbox': None,
                    'save_crossing_photo': False,
                    'crossing_timestamp': None
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
            
            # Store best frame (highest confidence)
            if conf > object_registry[track_id]['best_confidence']:
                object_registry[track_id]['best_confidence'] = conf
                object_registry[track_id]['best_frame'] = frame_sem_label.copy()
                object_registry[track_id]['best_frame_labeled'] = frame.copy()
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
                        print('=' * 70)
                        
                        # Marcar que deve salvar foto após desenhar labels
                        object_registry[track_id]['save_crossing_photo'] = True
                        object_registry[track_id]['crossing_timestamp'] = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
                        
                        # Upload images to Cloudinary and send analysis
                        if args.api_url or args.save_crossings:
                            try:
                                timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
                                filename_sem = f'analysis_{obj_uuid[:8]}_{timestamp}_normal.jpg'
                                filename_com = f'analysis_{obj_uuid[:8]}_{timestamp}_labeled.jpg'
                                
                                # Save best frames
                                best_frame = object_registry[track_id]['best_frame']
                                best_frame_labeled = object_registry[track_id]['best_frame_labeled']
                                
                                # Determine save path
                                if args.save_crossings:
                                    path_sem = os.path.join(args.output_dir, filename_sem)
                                    path_com = os.path.join(args.output_dir, filename_com)
                                    cv2.imwrite(path_sem, best_frame)
                                    cv2.imwrite(path_com, best_frame_labeled)
                                    print(f'💾 Imagens salvas em: {args.output_dir}/')
                                else:
                                    path_sem = os.path.join(os.getcwd(), filename_sem)
                                    path_com = os.path.join(os.getcwd(), filename_com)
                                    cv2.imwrite(path_sem, best_frame)
                                    cv2.imwrite(path_com, best_frame_labeled)
                                
                                # Upload to Cloudinary if API is configured
                                if args.api_url:
                                    print(f'📤 Enviando análise para Cloudinary...')
                                    
                                    # Upload to Cloudinary
                                    if args.unsigned:
                                        if not args.upload_preset:
                                            raise RuntimeError('--upload_preset required for unsigned uploads')
                                        resp_sem = cloudinary.uploader.upload(path_sem, folder='ache-capture/analysis', 
                                                                             upload_preset=args.upload_preset, 
                                                                             public_id=f'normal_{obj_uuid[:8]}_{timestamp}')
                                        resp_com = cloudinary.uploader.upload(path_com, folder='ache-capture/analysis', 
                                                                             upload_preset=args.upload_preset, 
                                                                             public_id=f'labeled_{obj_uuid[:8]}_{timestamp}')
                                    else:
                                        resp_sem = cloudinary.uploader.upload(path_sem, folder='ache-capture/analysis', 
                                                                             public_id=f'normal_{obj_uuid[:8]}_{timestamp}')
                                        resp_com = cloudinary.uploader.upload(path_com, folder='ache-capture/analysis', 
                                                                             public_id=f'labeled_{obj_uuid[:8]}_{timestamp}')
                                    
                                    # Prepare analysis product JSON (use majority class)
                                    product = {
                                        'id': track_id,
                                        'uuid': obj_uuid,
                                        'data': datetime.datetime.now().isoformat(),
                                        'tipo': majority_class,
                                        'aprovado': object_registry[track_id]['best_confidence'] > 0.7,
                                        'status': 'aprovado' if object_registry[track_id]['best_confidence'] > 0.7 else 'verificar',
                                        'veracidade': f"{int(object_registry[track_id]['best_confidence'] * 100)}%",
                                        'confianca': object_registry[track_id]['best_confidence'],
                                        'consenso': f"{vote_count}/{total_votes}",
                                        'consensoPercentual': vote_percent,
                                        'tempoVidaSegundos': round(lifetime, 2),
                                        'imgLabel': resp_com.get('secure_url'),
                                        'imgNormal': resp_sem.get('secure_url'),
                                        'cruzouLinha': True,
                                        'timestamp': timestamp
                                    }
                                    
                                    # Queue POST request
                                    post_timeout = None if (args.api_timeout <= 0) else args.api_timeout
                                    post_item = {
                                        'url': args.api_url,
                                        'json': product,
                                        'headers': {'Content-Type': 'application/json'},
                                        'timeout': post_timeout
                                    }
                                    post_queue.put_nowait(post_item)
                                    
                                    print(f'✅ Análise enfileirada para envio: {obj_uuid[:8]}...')
                                
                                # Clean up temp files only if not saving locally
                                if not args.save_crossings:
                                    if os.path.exists(path_sem):
                                        os.remove(path_sem)
                                    if os.path.exists(path_com):
                                        os.remove(path_com)
                                    
                            except Exception as e:
                                print(f'❌ Erro ao processar análise: {e}')
            
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
            
            # Salvar foto com labels SE o objeto acabou de cruzar a linha
            if object_registry[track_id].get('save_crossing_photo', False):
                obj_uuid = object_registry[track_id]['uuid']
                timestamp = object_registry[track_id]['crossing_timestamp']
                obj_class = object_registry[track_id]['class']
                filename_com = f'crossing_{obj_uuid[:8]}_{timestamp}_{obj_class}_labeled.jpg'
                
                if args.save_crossings or not args.api_url:
                    output_path = os.path.join(args.output_dir if args.save_crossings else os.getcwd(), filename_com)
                    cv2.imwrite(output_path, frame.copy())
                    print(f'📸 Foto com labels salva: {filename_com}')
                
                # Marcar como já salvo para não salvar novamente
                object_registry[track_id]['save_crossing_photo'] = False

    # Handle missing objects with hybrid solution (prediction, buffer, timeout)
    to_remove = handle_missing_objects(object_registry, active_tracks, trigger_x, 
                                      args.trigger_buffer, current_time, frame, 
                                      crossed_objects, args)

    for track_id in to_remove:
        del object_registry[track_id]
        # NÃO remover de crossed_objects - manter contagem de objetos que cruzaram
        # crossed_objects.discard(track_id)  # REMOVIDO para manter contagem correta

    # Draw buffer zone (semi-transparent yellow rectangle)
    if args.trigger_buffer > 0:
        overlay = frame.copy()
        cv2.rectangle(overlay, 
                     (trigger_x - args.trigger_buffer, 0), 
                     (trigger_x + args.trigger_buffer, frame.shape[0]),
                     (0, 255, 255), -1)  # Yellow filled
        cv2.addWeighted(overlay, 0.2, frame, 0.8, 0, frame)  # 20% transparency
        
        # Draw buffer zone borders
        cv2.line(frame, (trigger_x - args.trigger_buffer, 0), 
                (trigger_x - args.trigger_buffer, frame.shape[0]), (0, 255, 255), 1)
        cv2.line(frame, (trigger_x + args.trigger_buffer, 0), 
                (trigger_x + args.trigger_buffer, frame.shape[0]), (0, 255, 255), 1)
    
    # Draw trigger line (vertical, bright green)
    cv2.line(frame, (trigger_x, 0), (trigger_x, frame.shape[0]), (0, 255, 0), 3)
    
    # Put label near top of the line
    label_x = min(trigger_x + 10, frame.shape[1] - 150)
    cv2.putText(frame, 'TRIGGER LINE', (label_x, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
    if args.trigger_buffer > 0:
        cv2.putText(frame, f'Buffer: ±{args.trigger_buffer}px', (label_x, 45), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 1)

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
print(f'\nFPS médio: {avg_frame_rate:.2f}')
print(f'Total de objetos que cruzaram a linha: {len(crossed_objects)}')

if source_type in ['video', 'usb']:
    cap.release()
elif source_type == 'picamera':
    cap.stop()
if record: 
    recorder.release()
cv2.destroyAllWindows()

# Signal background poster to exit
post_queue.put(None)
post_queue.join()
print('Sistema finalizado.')

# Signal background poster to exit and wait for it to finish
post_queue.put(None)
post_queue.join()
