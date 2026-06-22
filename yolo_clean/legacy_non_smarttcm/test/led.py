import RPi.GPIO as GPIO
import time

# 设置GPIO口的编号模式
GPIO.setmode(GPIO.BCM)

# 设置GPIO26为输出模式
LED_PIN = 26
GPIO.setup(LED_PIN, GPIO.OUT)

for i in range(3):
    # 点亮3秒后熄灭
    GPIO.output(LED_PIN, GPIO.HIGH)
    print("LED亮起")
    time.sleep(3)

    GPIO.output(LED_PIN, GPIO.LOW)
    print("LED熄灭")
    time.sleep(3)

# 清理GPIO资源
GPIO.cleanup()