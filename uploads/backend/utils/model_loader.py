import logging
import os
import threading
from faster_whisper import WhisperModel
import torch

logger = logging.getLogger(__name__)


class ModelLoader:
    """
    模型載入器，提供每進程的模型快取。
    
    注意：
    - _instances 是每進程的全域變數，不同 worker 進程之間不共享
    - 在同一進程內的多線程環境下，使用 Lock 確保線程安全
    """
    _instances = {}
    _lock = threading.Lock()

    @classmethod
    def get_faster_whisper_model(cls, model_size="base"):
        with cls._lock:
            if model_size not in cls._instances:
                logger.info("Loading Faster-Whisper model: %s", model_size)
                # 自動偵測 GPU
                device = "cuda" if torch.cuda.is_available() else "cpu"
                # Faster-Whisper 支援 int8 量化以節省記憶體
                compute_type = "float16" if device == "cuda" else "int8"
                
                logger.info("Using device=%s compute_type=%s", device, compute_type)
                
                # 載入模型並快取
                cls._instances[model_size] = WhisperModel(
                    model_size, 
                    device=device, 
                    compute_type=compute_type
                )
            
            return cls._instances[model_size]

def get_model_by_duration(duration_seconds: float):
    """
    根據影片長度自動選擇模型
    """
    if duration_seconds < 60: # 小於 1 分鐘
        return "base"
    elif duration_seconds < 600: # 小於 10 分鐘
        return "small"
    else:
        return "medium" # 長影片使用更精準的模型

# 全域存取點
def get_model(model_size="base"):
    return ModelLoader.get_faster_whisper_model(model_size)
