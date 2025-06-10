import cv2
import os
import time
import torch
import torch.nn as nn
from torchvision import models, transforms
from PIL import Image
import requests
import tensorflow as tf
import numpy as np

# ✅ 设备配置
device_id = "RPi-01"
server_url = "http://10.20.135.28:5000/upload"  # ✅ 正确地址
capture_interval = 30  # 每 30 秒执行一次

# ✅ 类别标签
class_names = [
    "Pepper__bell___Bacterial_spot",
    "Pepper__bell___healthy",
    "Potato___Early_blight",
    "Potato___healthy",
    "Potato___Late_blight",
    "Tomato__Target_Spot",
    "Tomato__Tomato_mosaic_virus",
    "Tomato__Tomato_YellowLeaf__Curl_Virust",
    "Tomato_Bacterial_spot",
    "Tomato_Early_blight",
    "Tomato_healthy",
    "Tomato_Late_blight",
    "Tomato_Leaf_Mold",
    "Tomato_Septoria_leaf_spot",
    "Tomato_Spider_mites_Two_spotted_spider_mite"
]

growth_classes = ["seedling", "mature"]

# ✅ PyTorch 设置
torch_device = torch.device("cpu")
num_classes = len(class_names)
torch_transform = transforms.Compose([
    transforms.Resize((224, 224)),
    transforms.ToTensor(),
    transforms.Normalize([0.5, 0.5, 0.5], [0.5, 0.5, 0.5])
])

pytorch_model = models.resnet18()
pytorch_model.fc = nn.Linear(pytorch_model.fc.in_features, num_classes)
pytorch_model.load_state_dict(torch.load("bestone_0.2698.pth", map_location=torch_device))
pytorch_model = pytorch_model.to(torch_device)
pytorch_model.eval()

# ✅ TensorFlow 设置
tf_model = tf.keras.models.load_model("plant_growth_model.h5")

print("🚀 开始循环，每隔 30 秒拍照识别并上传（含图片）...\n按 Ctrl+C 停止")

while True:
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    safe_timestamp = timestamp.replace(":", "-").replace(" ", "_")
    img_path = f"plant_{safe_timestamp}.jpg"

    # 📸 拍照
    cap = cv2.VideoCapture(0)
    ret, frame = cap.read()
    if ret:
        cv2.imwrite(img_path, frame)
        print(f"\n📷 拍摄成功：{img_path}")
    else:
        print("❌ 摄像头拍照失败")
        cap.release()
        time.sleep(capture_interval)
        continue
    cap.release()

    # 🌿 健康状态预测（PyTorch）
    image_pil = Image.open(img_path).convert("RGB")
    input_tensor = torch_transform(image_pil).unsqueeze(0).to(torch_device)
    with torch.no_grad():
        output = pytorch_model(input_tensor)
        _, pred = torch.max(output, 1)
        health_status = class_names[pred.item()]
    print(f"🌿 健康状态识别结果：{health_status}")

    # 🌱 生长阶段预测（TensorFlow）
    img = cv2.imread(img_path)
    img_resized = cv2.resize(img, (224, 224)) / 255.0
    img_input = np.expand_dims(img_resized, axis=0)
    growth_pred = tf_model.predict(img_input, verbose=0)[0]
    growth_label = growth_classes[np.argmax(growth_pred)]
    print(f"🌱 生长阶段识别结果：{growth_label}")

    # 📤 上传数据准备
    payload = {
        "deviceID": device_id,
        "timestamp": timestamp,
        "prediction": health_status,
        "growthStage": growth_label
    }

    # 🛜 上传 + 重试逻辑
    max_retries = 3
    success = False
    for attempt in range(max_retries):
        try:
            with open(img_path, "rb") as image_file:
                files = {"image": image_file}
                response = requests.post(server_url, data=payload, files=files, timeout=5)

            if response.status_code == 200:
                print(f"✅ 上传成功：{response.status_code} - {response.text}")
                success = True
                break
            else:
                print(f"⚠️ 上传失败（状态码 {response.status_code}）：{response.text}")
        except Exception as e:
            print(f"⚠️ 第 {attempt + 1} 次上传失败：{e}")
            time.sleep(2)

    # ✅ 成功后删除图片
    if success:
        os.remove(img_path)
        print(f"🧹 已删除图片：{img_path}")
    else:
        print(f"🚫 本轮上传失败，保留图片以便排查")

    time.sleep(capture_interval)

