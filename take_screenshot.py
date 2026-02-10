import mss
import mss.tools
import os

# 创建 screenshots 目录
screenshot_dir = "screenshots"
os.makedirs(screenshot_dir, exist_ok=True)

# 截图路径
screenshot_path = os.path.join(screenshot_dir, "screen.png")

# 使用 mss 截图
with mss.mss() as sct:
    # 获取所有显示器
    monitors = sct.monitors
    print(f"找到 {len(monitors)} 个显示器")
    
    # 截图主显示器（索引 1，因为索引 0 是所有显示器的组合）
    monitor = monitors[1] if len(monitors) > 1 else monitors[0]
    
    # 截图
    screenshot = sct.grab(monitor)
    
    # 保存为 PNG
    mss.tools.to_png(screenshot.rgb, screenshot.size, output=screenshot_path)
    
    print(f"截图已保存到: {screenshot_path}")
    print(f"文件大小: {os.path.getsize(screenshot_path)} 字节")