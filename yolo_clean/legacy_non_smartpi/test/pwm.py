import RPi.GPIO as GPIO  # 导入树莓派 GPIO 库
import time  # 导入时间模块，用于延时

LED_PIN = 26  # 设置 LED 引脚为 GPIO16（物理引脚号为 36）

# 设置 GPIO 编号模式为 BCM（Broadcom 芯片编号）
GPIO.setmode(GPIO.BCM)

# 设置 GPIO16 为输出模式
GPIO.setup(LED_PIN, GPIO.OUT)

# 创建一个 PWM 对象，频率设置为 1000Hz（1kHz）
pwm = GPIO.PWM(LED_PIN, 1000)

# 启动 PWM，初始占空比为 0%（即 LED 熄灭）
pwm.start(0)

try:
    while True:
        # LED 亮度逐渐增加
        for dc in range(0, 101, 1):  # 占空比从 0% 到 100%
            pwm.ChangeDutyCycle(dc)  # 修改占空比，实现亮度变化
            time.sleep(0.02)  # 延时 20 毫秒，控制变化速度

        # LED 亮度逐渐减小
        for dc in range(100, -1, -1):  # 占空比从 100% 降到 0%
            pwm.ChangeDutyCycle(dc)
            time.sleep(0.02)
except KeyboardInterrupt:
    # 当用户按下 Ctrl+C 中断程序时，执行清理操作
    pass

# 停止 PWM 信号输出
pwm.stop()

# 清理所有 GPIO 设置，释放资源
GPIO.cleanup()