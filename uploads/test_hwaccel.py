import os
import sys
import logging

# 加入 backend 到 path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), ".")))

from backend.utils.video_utils import get_hwaccel_params

logging.basicConfig(level=logging.INFO)

def test_hwaccel_detection():
    print("Testing hardware acceleration detection...")
    params = get_hwaccel_params()
    print(f"Detected parameters: {params}")
    
    # 在 sandbox 環境中，通常沒有 GPU，預期會 fallback 到 libx264
    if "-c:v" in params:
        idx = params.index("-c:v")
        encoder = params[idx + 1]
        print(f"✓ Encoder selected: {encoder}")
    else:
        print("✗ Failed to find encoder in params")

if __name__ == "__main__":
    test_hwaccel_detection()
