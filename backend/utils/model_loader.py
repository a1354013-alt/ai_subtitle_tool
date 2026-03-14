import torch
from faster_whisper import WhisperModel

class ModelLoader:
    _instances = {}

    @classmethod
    def get_faster_whisper_model(cls, model_size="base"):
        if model_size not in cls._instances:
            print(f"Loading Faster-Whisper model: {model_size}...")
            # 自動偵測 GPU
            device = "cuda" if torch.cuda.is_available() else "cpu"
            # Faster-Whisper 支援 int8 量化以節省記憶體
            compute_type = "float16" if device == "cuda" else "int8"
            
            print(f"Using device: {device}, compute_type: {compute_type}")
            
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
