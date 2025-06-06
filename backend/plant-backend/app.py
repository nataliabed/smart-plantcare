from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
from pymongo import MongoClient
from datetime import datetime
import os
import io
import csv

app = Flask(__name__)
CORS(app)

# ✅ MongoDB 配置
MONGO_URI = os.environ.get('MONGO_URI') or "mongodb+srv://student:austral-clash-sawyer-blaze@espplantcluster.3yopiy3.mongodb.net/?retryWrites=true&w=majority&appName=ESPPlantCluster"
client = MongoClient(MONGO_URI)
db = client["esp_data"]
collection = db["moisture_readings"]
prediction_collection = db["plant_predictions"]

# ✅ 上传湿度或识别数据
@app.route("/upload", methods=["POST"])
def upload_data():
    # 树莓派上传：multipart/form-data（图像识别 + 图片）
    if request.content_type.startswith("multipart/form-data"):
        form = request.form
        device_id = form.get("deviceID")
        prediction = form.get("prediction")
        growth_stage = form.get("growthStage")
        timestamp_str = form.get("timestamp")

        if not device_id or not prediction or not growth_stage or not timestamp_str:
            return jsonify({"error": "Missing required fields"}), 400

        # 可选保存图片
        image = request.files.get("image")
        image_path = None
        if image:
            os.makedirs("uploads", exist_ok=True)
            filename = f"{device_id}_{timestamp_str.replace(':', '-')}.jpg"
            image_path = os.path.join("uploads", filename)
            image.save(image_path)

        # 构造数据并写入 MongoDB
        data = {
            "deviceID": device_id,
            "prediction": prediction,
            "growthStage": growth_stage,
            "timestamp": datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S"),
            "date": datetime.utcnow().strftime("%Y-%m-%d")
        }
        if image_path:
            data["imagePath"] = image_path

        prediction_collection.insert_one(data)
        print(f"✅ 树莓派识别数据已存储: {data}")
        return jsonify({"message": "Prediction data stored"}), 200

    # ESP32 上传：application/json（湿度数据）
    else:
        data = request.get_json()
        if not data or "deviceID" not in data or "avgMoisture" not in data:
            return jsonify({"error": "Invalid ESP32 payload"}), 400

        now = datetime.utcnow()
        data["timestamp"] = now
        data["date"] = now.strftime("%Y-%m-%d")
        collection.insert_one(data)
        print(f"✅ ESP32 湿度数据已存储: {data}")
        return jsonify({"message": "Moisture data stored"}), 200

# ✅ 获取识别数据
@app.route("/predictions", methods=["GET"])
def get_predictions():
    device_id = request.args.get("deviceID")
    query = {"deviceID": device_id} if device_id else {}
    data = list(prediction_collection.find(query, {"_id": 0}))
    return jsonify(data), 200

# ✅ 获取湿度数据
@app.route("/data", methods=["GET"])
def get_data():
    device_id = request.args.get("deviceID")
    query = {"deviceID": device_id} if device_id else {}
    data = list(collection.find(query, {"_id": 0}))
    return jsonify(data), 200

# ✅ 下载湿度数据为 CSV
@app.route("/download", methods=["GET"])
def download_csv():
    device_id = request.args.get("deviceID")
    query = {"deviceID": device_id} if device_id else {}
    data = list(collection.find(query, {"_id": 0}))

    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=["deviceID", "avgMoisture", "timestamp", "date"])
    writer.writeheader()
    for row in data:
        writer.writerow(row)

    output.seek(0)
    return send_file(
        io.BytesIO(output.getvalue().encode()),
        mimetype="text/csv",
        as_attachment=True,
        download_name="moisture_data.csv"
    )

# ✅ 启动服务器
if __name__ == '__main__':
    os.makedirs("uploads", exist_ok=True)
    app.run(host='0.0.0.0', port=5000)
