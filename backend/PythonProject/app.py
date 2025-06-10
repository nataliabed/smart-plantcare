from flask import Flask, request, jsonify, send_file, abort
from flask_cors import CORS
from pymongo import MongoClient, errors
from datetime import datetime, timedelta
import os
import io
import csv
import re
import logging

app = Flask(__name__)
CORS(app)

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ESPPlantBackend")

# ✅ 安全获取MongoDB配置
MONGO_URI = "mongodb+srv://student:austral-clash-sawyer-blaze@espplantcluster.3yopiy3.mongodb.net/?retryWrites=true&w=majority&appName=ESPPlantCluster"
if not MONGO_URI:
    logger.error("MongoDB URI not found in environment variables")
    raise RuntimeError("MongoDB URI must be set in environment variables")

try:
    client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
    client.server_info()  # 测试连接
    db = client["esp_data"]
    collection = db["moisture_readings"]
    prediction_collection = db["plant_predictions"]
    logger.info("✅ Successfully connected to MongoDB")
except errors.ServerSelectionTimeoutError as e:
    logger.error(f"MongoDB connection failed: {str(e)}")
    raise RuntimeError("Database connection failed") from e

# 配置常量
MAX_IMAGE_SIZE = 5 * 1024 * 1024  # 5MB
ALLOWED_EXTENSIONS = {'jpg', 'jpeg', 'png'}


def allowed_file(filename):
    return '.' in filename and \
        filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def validate_device_id(device_id):
    """验证设备ID格式 (ESP32_XXXXXX)"""
    return re.match(r'^ESP32_[A-Z0-9]{6}$', device_id) is not None


# ✅ 上传湿度或识别数据
@app.route("/upload", methods=["POST"])
def upload_data():
    try:
        # 树莓派上传：multipart/form-data
        if request.content_type.startswith("multipart/form-data"):
            form = request.form
            device_id = form.get("deviceID")
            prediction = form.get("prediction")
            growth_stage = form.get("growthStage")
            timestamp_str = form.get("timestamp")

            # 验证必需字段
            if not all([device_id, prediction, growth_stage, timestamp_str]):
                logger.warning("Missing required fields in Raspberry Pi upload")
                return jsonify({"error": "Missing required fields"}), 400

            # 验证设备ID格式
            if not validate_device_id(device_id):
                logger.warning(f"Invalid device ID format: {device_id}")
                return jsonify({"error": "Invalid device ID format"}), 400

            # 尝试解析时间戳
            try:
                timestamp = datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S")
            except ValueError:
                logger.warning(f"Invalid timestamp format: {timestamp_str}")
                return jsonify({"error": "Invalid timestamp format. Use YYYY-MM-DD HH:MM:SS"}), 400

            # 处理图片上传
            image = request.files.get("image")
            image_filename = None

            if image:
                # 验证图片
                if image.content_length > MAX_IMAGE_SIZE:
                    logger.warning(f"Image too large: {image.content_length} bytes")
                    return jsonify({"error": "Image exceeds 5MB size limit"}), 413

                if not allowed_file(image.filename):
                    logger.warning(f"Invalid image type: {image.filename}")
                    return jsonify({"error": "Invalid image type. Allowed: JPG, JPEG, PNG"}), 400

                # 安全保存图片
                os.makedirs("uploads", exist_ok=True)
                filename = f"{device_id}_{timestamp.strftime('%Y%m%d_%H%M%S')}.jpg"
                image_path = os.path.join("uploads", filename)
                image.save(image_path)
                image_filename = filename
                logger.info(f"Saved image: {image_path}")

            # 构造数据
            data = {
                "deviceID": device_id,
                "prediction": prediction,
                "growthStage": growth_stage,
                "timestamp": timestamp,
                "serverTimestamp": datetime.utcnow(),
                "date": datetime.utcnow().strftime("%Y-%m-%d")
            }

            if image_filename:
                data["imageFilename"] = image_filename

            # 插入数据库
            prediction_collection.insert_one(data)
            logger.info(f"✅ Raspberry Pi data stored for device {device_id}")
            return jsonify({"message": "Prediction data stored"}), 200

        # ESP32 上传：application/json
        else:
            data = request.get_json()
            if not data or "deviceID" not in data or "avgMoisture" not in data:
                logger.warning("Invalid ESP32 payload")
                return jsonify({"error": "Invalid payload. Requires deviceID and avgMoisture"}), 400

            # 验证设备ID格式
            if not validate_device_id(data["deviceID"]):
                logger.warning(f"Invalid device ID format: {data['deviceID']}")
                return jsonify({"error": "Invalid device ID format"}), 400

            # 添加时间戳
            now = datetime.utcnow()
            data["timestamp"] = now
            data["serverTimestamp"] = now
            data["date"] = now.strftime("%Y-%m-%d")

            # 插入数据库
            collection.insert_one(data)
            logger.info(f"✅ ESP32 moisture data stored for device {data['deviceID']}")
            return jsonify({"message": "Moisture data stored"}), 200

    except Exception as e:
        logger.error(f"Upload failed: {str(e)}", exc_info=True)
        return jsonify({"error": "Internal server error"}), 500


# ✅ 获取识别数据
@app.route("/predictions", methods=["GET"])
def get_predictions():
    try:
        device_id = request.args.get("deviceID")
        limit = int(request.args.get("limit", 100))

        query = {"deviceID": device_id} if device_id else {}

        # 添加时间过滤
        if days := request.args.get("days"):
            try:
                days = int(days)
                time_filter = {"timestamp": {"$gte": datetime.utcnow() - timedelta(days=days)}}
                query = {**query, **time_filter}
            except ValueError:
                pass

        projection = {"_id": 0}
        data = list(prediction_collection.find(query, projection).sort("timestamp", -1).limit(limit))

        # 添加图片URL
        for item in data:
            if "imageFilename" in item:
                item["imageUrl"] = f"/image/{item['imageFilename']}"

        return jsonify(data), 200

    except Exception as e:
        logger.error(f"Get predictions failed: {str(e)}")
        return jsonify({"error": "Internal server error"}), 500


# ✅ 获取湿度数据
@app.route("/data", methods=["GET"])
def get_data():
    try:
        device_id = request.args.get("deviceID")
        limit = int(request.args.get("limit", 500))

        query = {"deviceID": device_id} if device_id else {}

        # 添加时间过滤
        if hours := request.args.get("hours"):
            try:
                hours = int(hours)
                time_filter = {"timestamp": {"$gte": datetime.utcnow() - timedelta(hours=hours)}}
                query = {**query, **time_filter}
            except ValueError:
                pass

        projection = {"_id": 0}
        data = list(collection.find(query, projection).sort("timestamp", -1).limit(limit))
        return jsonify(data), 200

    except Exception as e:
        logger.error(f"Get data failed: {str(e)}")
        return jsonify({"error": "Internal server error"}), 500


# ✅ 下载湿度数据为CSV
@app.route("/download", methods=["GET"])
def download_csv():
    try:
        device_id = request.args.get("deviceID")
        if not device_id:
            return jsonify({"error": "deviceID is required"}), 400

        query = {"deviceID": device_id}

        # 添加日期范围过滤
        if start_date := request.args.get("start"):
            try:
                start = datetime.strptime(start_date, "%Y-%m-%d")
                query["date"] = {"$gte": start_date}
            except ValueError:
                pass

        data = list(collection.find(query, {"_id": 0}))

        if not data:
            return jsonify({"error": "No data found"}), 404

        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=data[0].keys())
        writer.writeheader()
        writer.writerows(data)

        output.seek(0)
        filename = f"moisture_data_{device_id}_{datetime.utcnow().strftime('%Y%m%d')}.csv"

        return send_file(
            io.BytesIO(output.getvalue().encode()),
            mimetype="text/csv",
            as_attachment=True,
            download_name=filename
        )

    except Exception as e:
        logger.error(f"CSV download failed: {str(e)}")
        return jsonify({"error": "Internal server error"}), 500


# ✅ 图片访问接口
@app.route("/image/<filename>", methods=["GET"])
def get_image(filename):
    try:
        # 防止路径遍历攻击
        if ".." in filename or filename.startswith("/"):
            abort(400, "Invalid filename")

        path = os.path.join("uploads", filename)

        if not os.path.exists(path):
            abort(404, "Image not found")

        return send_file(path, mimetype='image/jpeg')

    except Exception as e:
        logger.error(f"Image retrieval failed: {str(e)}")
        return jsonify({"error": "Internal server error"}), 500


# ✅ 数据清理端点 (保护性端点)
@app.route("/cleanup", methods=["POST"])
def cleanup_data():
    # 在实际部署中应添加身份验证
    try:
        days = int(request.json.get("days", 30))
        cutoff_date = datetime.utcnow() - timedelta(days=days)

        # 删除旧湿度记录
        moisture_result = collection.delete_many({
            "timestamp": {"$lt": cutoff_date}
        })

        # 删除旧预测记录
        prediction_result = prediction_collection.delete_many({
            "timestamp": {"$lt": cutoff_date}
        })

        # 删除旧图片
        image_count = 0
        for filename in os.listdir("uploads"):
            filepath = os.path.join("uploads", filename)
            file_time = datetime.fromtimestamp(os.path.getmtime(filepath))
            if file_time < cutoff_date:
                os.remove(filepath)
                image_count += 1

        return jsonify({
            "message": "Cleanup completed",
            "deleted_moisture": moisture_result.deleted_count,
            "deleted_predictions": prediction_result.deleted_count,
            "deleted_images": image_count
        }), 200

    except Exception as e:
        logger.error(f"Cleanup failed: {str(e)}")
        return jsonify({"error": "Internal server error"}), 500


# ✅ 启动服务器
if __name__ == '__main__':
    os.makedirs("uploads", exist_ok=True)
    logger.info("Starting server on 0.0.0.0:5000")
    app.run(host='0.0.0.0', port=5000)