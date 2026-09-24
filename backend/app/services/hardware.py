"""
Hardware detection service.
Detects CPU, RAM, GPU, VRAM, and selects ONNX execution provider.
"""

import platform
import psutil
import subprocess
from app.core.logger import get_logger

logger = get_logger(__name__)


class HardwareService:
    def __init__(self):
        self.cpu_name: str = "Unknown"
        self.cpu_cores: int = 0
        self.ram_gb: float = 0.0
        self.gpu_name: str = "None"
        self.vram_gb: float = 0.0
        self.acceleration: str = "CPUExecutionProvider"
        self._detected = False

    def detect(self) -> None:
        self._detect_cpu()
        self._detect_ram()
        self._detect_gpu()
        self._select_provider()
        self._detected = True

    def _detect_cpu(self) -> None:
        try:
            with open("/proc/cpuinfo") as f:
                for line in f:
                    if "model name" in line:
                        self.cpu_name = line.split(":")[1].strip()
                        break
        except Exception:
            self.cpu_name = platform.processor() or "Unknown"
        self.cpu_cores = psutil.cpu_count(logical=True) or 0

    def _detect_ram(self) -> None:
        mem = psutil.virtual_memory()
        self.ram_gb = round(mem.total / (1024 ** 3), 1)

    def _detect_gpu(self) -> None:
        # Try nvidia-smi
        try:
            result = subprocess.run(
                ["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"],
                capture_output=True, text=True, timeout=5,
            )
            if result.returncode == 0 and result.stdout.strip():
                parts = result.stdout.strip().split(",")
                self.gpu_name = parts[0].strip()
                self.vram_gb = round(float(parts[1].strip()) / 1024, 1)
                return
        except Exception:
            pass

        # Try ROCm (AMD)
        try:
            result = subprocess.run(
                ["rocm-smi", "--showproductname"],
                capture_output=True, text=True, timeout=5,
            )
            if result.returncode == 0 and result.stdout.strip():
                self.gpu_name = "AMD GPU (ROCm)"
                return
        except Exception:
            pass

        self.gpu_name = "None"

    def _select_provider(self) -> None:
        try:
            import onnxruntime as ort
            available = ort.get_available_providers()
            logger.info("onnx_providers_available", providers=available)

            if "CUDAExecutionProvider" in available:
                self.acceleration = "CUDAExecutionProvider"
            elif "ROCMExecutionProvider" in available:
                self.acceleration = "ROCMExecutionProvider"
            elif "OpenVINOExecutionProvider" in available:
                self.acceleration = "OpenVINOExecutionProvider"
            else:
                self.acceleration = "CPUExecutionProvider"
        except ImportError:
            self.acceleration = "CPUExecutionProvider"

        logger.info("acceleration_selected", provider=self.acceleration)

    def summary(self) -> dict:
        return {
            "cpu": self.cpu_name,
            "cpu_cores": self.cpu_cores,
            "ram_gb": self.ram_gb,
            "gpu": self.gpu_name,
            "vram_gb": self.vram_gb,
            "acceleration": self.acceleration,
        }

    def get_onnx_providers(self) -> list:
        providers = []
        if self.acceleration == "CUDAExecutionProvider":
            providers.append("CUDAExecutionProvider")
        elif self.acceleration == "ROCMExecutionProvider":
            providers.append("ROCMExecutionProvider")
        providers.append("CPUExecutionProvider")
        return providers


hardware_service = HardwareService()
