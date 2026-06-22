import cv2
from picamera2 import Picamera2
from ultralytics import YOLO
import time

# Initialize the Picamera2
picam2 = Picamera2()
picam2.preview_configuration.main.size = (640, 480)
picam2.preview_configuration.main.format = "RGB888"
picam2.preview_configuration.align()
picam2.configure("preview")
picam2.start()

# Load the YOLO11 model
model = YOLO("yolo11n_ncnn_model")

# 初始化帧率计算变量
frame_count = 0
start_time = time.time()
fps = 0

while True:
    # 捕获帧
    frame = picam2.capture_array()
    
    # 运行 YOLO 推理
    results = model(frame)
    
    # 可视化结果
    annotated_frame = results[0].plot()
    
    # 计算帧率
    frame_count += 1
    if frame_count >= 10:  # 每10帧计算一次FPS
        end_time = time.time()
        fps = frame_count / (end_time - start_time)
        frame_count = 0
        start_time = time.time()
    
    # 在图像上显示帧率
    fps_text = f"FPS: {fps:.2f}"
    cv2.putText(annotated_frame, fps_text, (10, 30), 
                cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
    
    # 显示结果
    cv2.imshow("Camera", annotated_frame)
    
    # 退出条件
    if cv2.waitKey(1) == ord("q"):
        break

# Release resources and close windows
cv2.destroyAllWindows()