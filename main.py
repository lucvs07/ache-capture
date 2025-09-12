import os
from dotenv import load_dotenv
import cloudinary
import cloudinary.uploader
from cloudinary.utils import cloudinary_url
import cv2
import datetime
import sys
import argparse
import glob
import time

import cv2
import numpy as np
from ultralytics import YOLO

load_dotenv()
# Configuration       
cloudinary.config( 
    cloud_name = os.getenv("CLOUDINARY_CLOUD_NAME"), 
    api_key = os.getenv("CLOUDINARY_API_KEY"), 
    api_secret = os.getenv("CLOUDINARY_API_SECRET"),
    secure=True
)

cap = cv2.VideoCapture(0)

# Verificar se a webcam foi aberta corretamente
if not cap.isOpened():
    print("Erro: Não foi possível abrir a webcam.")
    exit()

print("Webcam inicializada. Pressione 's' para tirar uma foto e 'q' para sair.")

# Loop principal para exibir o feed e capturar fotos
while True:
    # Ler um frame da webcam
    ret, frame = cap.read()

    # Se o frame não foi lido corretamente, sair do loop
    if not ret:
        print("Erro: Não foi possível ler o frame da webcam. Encerrando...")
        break

    # Exibir o frame em uma janela chamada 'Webcam Feed'
    cv2.imshow('Webcam Feed - Pressione S para foto, Q para sair', frame)

    # Capturar a tecla pressionada
    key = cv2.waitKey(1) & 0xFF  # cv2.waitKey(1) retorna -1 se nenhuma tecla for pressionada

    # Se a tecla 's' for pressionada, tirar a foto e fazer o upload
    if key == ord('s'):
        # Gerar um nome de arquivo único para a imagem
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"ache_capture_{timestamp}.jpg"
        temp_filepath = os.path.join(os.getcwd(), filename) # Salvar na pasta atual

        # Salvar o frame como um arquivo temporário JPG
        cv2.imwrite(temp_filepath, frame)
        print(f"Foto salva temporariamente como: {filename}")

        # --- 3. Fazer o Upload para o Cloudinary ---
        try:
            print(f"Fazendo upload de '{filename}' para o Cloudinary...")
            # O upload_preset é opcional, mas útil para aplicar regras de transformação
            # ou organizar as imagens em pastas no Cloudinary.
            # Se você não tiver um, pode remover o parâmetro `upload_preset`.
            # Ex: `response = cloudinary.uploader.upload(temp_filepath)`
            response = cloudinary.uploader.upload(temp_filepath, folder="ache-capture", public_id=f"capture_{timestamp}")

            # Imprimir a URL da imagem no Cloudinary
            image_url = response['secure_url']
            print(f"Upload bem-sucedido! URL da imagem: {image_url}")

            # Você pode adicionar aqui o código para enviar esta URL para sua API Node.js/Express
            # Por exemplo, usando a biblioteca 'requests':
            # import requests
            # api_data = {"imageUrl": image_url, "timestamp": timestamp}
            # requests.post("http://localhost:3000/api/images", json=api_data) # Substitua pela sua URL da API

        except cloudinary.exceptions.Error as e:
            print(f"Erro ao fazer upload para o Cloudinary: {e}")
        except Exception as e:
            print(f"Ocorreu um erro inesperado durante o upload: {e}")
        finally:
            # Remover o arquivo temporário após o upload (ou em caso de erro)
            if os.path.exists(temp_filepath):
                os.remove(temp_filepath)
                print(f"Arquivo temporário '{filename}' removido.")

    # Se a tecla 'q' for pressionada, sair do loop
    elif key == ord('q'):
        print("Saindo do programa...")
        break

# --- 4. Limpeza ---
# Liberar os recursos da webcam
cap.release()
# Fechar todas as janelas do OpenCV
cv2.destroyAllWindows()
print("Recursos liberados.")