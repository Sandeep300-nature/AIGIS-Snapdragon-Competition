import os
import platform
import psutil
import shutil
import subprocess
from typing import Dict, Any, List, Optional

try:
    import winreg
except ImportError:
    winreg = None

try:
    import onnxruntime
except ImportError:
    onnxruntime = None

try:
    import torch
except ImportError:
    torch = None


class HardwareDetector:
    """
    Truthful, hardware-aware capability detection layer for AIGIS.
    Distinguishes current development environments (x64 with NVIDIA GPU)
    from future Snapdragon Windows-on-Arm deployment environments.

    ZERO FABRICATION: Reports only dynamically verified physical and runtime capabilities.
    """

    @staticmethod
    def get_os_info() -> Dict[str, Any]:
        """Detects OS name, release version, and platform string."""
        return {
            "system": platform.system(),
            "release": platform.release(),
            "version": platform.version(),
            "platform": platform.platform()
        }

    @staticmethod
    def get_architecture() -> Dict[str, Any]:
        """Detects CPU machine architecture (e.g. AMD64/x86_64 vs ARM64)."""
        raw_machine = platform.machine()
        normalized = "x86_64" if raw_machine.upper() in ["AMD64", "X86_64"] else raw_machine
        is_arm64 = raw_machine.upper() in ["ARM64", "AARCH64"]
        is_x64 = raw_machine.upper() in ["AMD64", "X86_64"]

        return {
            "raw": raw_machine,
            "normalized": normalized,
            "isX64": is_x64,
            "isArm64": is_arm64
        }

    @staticmethod
    def get_cpu_info() -> Dict[str, Any]:
        """Detects CPU brand, architecture model, and physical/logical core counts."""
        raw_processor = platform.processor()
        brand_string = None

        if winreg and platform.system() == "Windows":
            try:
                key = winreg.OpenKey(
                    winreg.HKEY_LOCAL_MACHINE,
                    r"HARDWARE\DESCRIPTION\System\CentralProcessor\0"
                )
                val, _ = winreg.QueryValueEx(key, "ProcessorNameString")
                winreg.CloseKey(key)
                if val and isinstance(val, str):
                    brand_string = val.strip()
            except Exception:
                pass

        if not brand_string:
            brand_string = raw_processor or "Unknown CPU"

        physical_cores = psutil.cpu_count(logical=False) or 0
        logical_cores = psutil.cpu_count(logical=True) or 0

        # Check if CPU string indicates Qualcomm or Snapdragon
        lower_brand = brand_string.lower()
        lower_proc = raw_processor.lower()
        is_snapdragon = any(
            kw in lower_brand or kw in lower_proc
            for kw in ["snapdragon", "qualcomm", "sc8", "kryo", "x elite", "x plus"]
        )

        return {
            "brand": brand_string,
            "model": raw_processor,
            "physicalCores": physical_cores,
            "logicalCores": logical_cores,
            "isSnapdragon": is_snapdragon
        }

    @staticmethod
    def get_memory_info() -> Dict[str, Any]:
        """Detects total and available system RAM."""
        try:
            vm = psutil.virtual_memory()
            total_gb = round(vm.total / (1024 ** 3), 2)
            avail_gb = round(vm.available / (1024 ** 3), 2)
            used_gb = round(vm.used / (1024 ** 3), 2)
            return {
                "totalBytes": vm.total,
                "totalGb": total_gb,
                "availableGb": avail_gb,
                "usedGb": used_gb,
                "percentUsed": round(vm.percent, 1)
            }
        except Exception as e:
            return {
                "totalBytes": 0,
                "totalGb": 0.0,
                "availableGb": 0.0,
                "usedGb": 0.0,
                "percentUsed": 0.0,
                "error": str(e)
            }

    @staticmethod
    def get_gpu_info() -> Dict[str, Any]:
        """
        Dynamically detects physical GPU without hardcoding.
        Probes nvidia-smi first; falls back to Windows WMIC / PowerShell if non-NVIDIA.
        """
        # 1. Probe NVIDIA GPU via nvidia-smi
        if shutil.which("nvidia-smi"):
            try:
                cmd = [
                    "nvidia-smi",
                    "--query-gpu=name,driver_version,memory.total,utilization.gpu",
                    "--format=csv,noheader,nounits"
                ]
                output = subprocess.check_output(cmd, text=True, timeout=2.0).strip()
                lines = output.splitlines()
                if lines:
                    parts = [p.strip() for p in lines[0].split(",")]
                    if len(parts) >= 3:
                        name = parts[0]
                        driver = parts[1]
                        vram_mb = int(float(parts[2])) if parts[2].replace('.', '', 1).isdigit() else 0
                        vram_gb = round(vram_mb / 1024.0, 1)
                        utilization = int(float(parts[3])) if len(parts) > 3 and parts[3].replace('.', '', 1).isdigit() else 0

                        return {
                            "detected": True,
                            "vendor": "NVIDIA",
                            "name": name,
                            "driverVersion": driver,
                            "vramTotalMb": vram_mb,
                            "vramTotalGb": vram_gb,
                            "utilizationPercent": utilization,
                            "detectionMethod": "nvidia-smi"
                        }
            except Exception:
                pass

        # 2. Fallback: Windows PowerShell display adapter probe (for Intel/AMD/Qualcomm Adreno)
        if platform.system() == "Windows":
            try:
                ps_cmd = [
                    "powershell", "-NoProfile", "-Command",
                    "Get-CimInstance Win32_VideoController | Select-Object -First 1 Name, DriverVersion, AdapterRAM | ConvertTo-Json"
                ]
                out = subprocess.check_output(ps_cmd, text=True, timeout=3.0).strip()
                import json
                data = json.loads(out)
                name = data.get("Name", "Unknown GPU")
                driver = data.get("DriverVersion", "N/A")
                adapter_ram = data.get("AdapterRAM", 0) or 0
                vram_gb = round(adapter_ram / (1024 ** 3), 1)

                vendor = "Qualcomm" if "adreno" in name.lower() or "qualcomm" in name.lower() else (
                    "Intel" if "intel" in name.lower() else (
                        "AMD" if "amd" in name.lower() or "radeon" in name.lower() else "Unknown"
                    )
                )

                return {
                    "detected": True,
                    "vendor": vendor,
                    "name": name,
                    "driverVersion": driver,
                    "vramTotalMb": round(adapter_ram / (1024 ** 2)),
                    "vramTotalGb": vram_gb,
                    "detectionMethod": "Win32_VideoController"
                }
            except Exception:
                pass

        return {
            "detected": False,
            "vendor": "None",
            "name": "No discrete GPU detected",
            "driverVersion": "N/A",
            "vramTotalMb": 0,
            "vramTotalGb": 0.0,
            "detectionMethod": "none"
        }

    @staticmethod
    def get_onnxruntime_info() -> Dict[str, Any]:
        """Detects installed ONNX Runtime version and registered execution providers."""
        if not onnxruntime:
            return {
                "installed": False,
                "version": "Not installed",
                "availableProviders": [],
                "hasCudaProvider": False,
                "hasQnnProvider": False,
                "hasDirectMlProvider": False,
                "hasCpuProvider": False
            }

        version = getattr(onnxruntime, "__version__", "Unknown")
        try:
            providers = onnxruntime.get_available_providers()
        except Exception:
            providers = []

        return {
            "installed": True,
            "version": version,
            "availableProviders": providers,
            "hasCudaProvider": "CUDAExecutionProvider" in providers,
            "hasQnnProvider": "QNNExecutionProvider" in providers,
            "hasDirectMlProvider": "DmlExecutionProvider" in providers,
            "hasCpuProvider": "CPUExecutionProvider" in providers
        }

    @staticmethod
    def get_cuda_status(gpu_info: Dict[str, Any], ort_info: Dict[str, Any]) -> Dict[str, Any]:
        """
        Tests NVIDIA CUDA availability independently.
        Never assumes NVIDIA GPU presence implies functional CUDA in Python or ONNX.
        """
        torch_cuda_available = False
        torch_cuda_device_count = 0
        torch_cuda_device_name = None

        if torch:
            try:
                torch_cuda_available = torch.cuda.is_available()
                if torch_cuda_available:
                    torch_cuda_device_count = torch.cuda.device_count()
                    if torch_cuda_device_count > 0:
                        torch_cuda_device_name = torch.cuda.get_device_name(0)
            except Exception:
                torch_cuda_available = False

        ort_cuda_available = ort_info.get("hasCudaProvider", False)
        hw_detected = gpu_info.get("vendor") == "NVIDIA" and gpu_info.get("detected", False)

        if torch_cuda_available and ort_cuda_available:
            status = "Functional (PyTorch CUDA & ONNX Runtime CUDA Execution Provider active)"
        elif torch_cuda_available:
            status = "PyTorch CUDA functional; ONNX Runtime CUDA provider not registered"
        elif ort_cuda_available:
            status = "ONNX Runtime CUDA provider registered; PyTorch CUDA not active"
        elif hw_detected:
            status = "NVIDIA GPU physically present, but CUDA execution runtime not installed/active in Python/ONNX"
        else:
            status = "Not available (no NVIDIA hardware or CUDA runtime)"

        return {
            "hardwareDetected": hw_detected,
            "torchCudaAvailable": torch_cuda_available,
            "torchCudaDeviceCount": torch_cuda_device_count,
            "torchCudaDeviceName": torch_cuda_device_name,
            "onnxruntimeCudaAvailable": ort_cuda_available,
            "status": status
        }

    @staticmethod
    def get_qnn_status(ort_info: Dict[str, Any]) -> Dict[str, Any]:
        """
        Tests Qualcomm Neural Network (QNN) runtime & execution provider availability independently.
        Never assumes Snapdragon implies QNN, or that QNN DLLs imply functional execution.
        """
        ort_qnn_available = ort_info.get("hasQnnProvider", False)

        # Check for QNN SDK environment variables
        qnn_sdk_root = os.environ.get("QNN_SDK_ROOT") or os.environ.get("QUALCOMM_SDK_ROOT")

        # Check for QNN HTP / CPU runtime DLLs in PATH
        qnn_dlls = ["QnnHtp.dll", "QnnCpu.dll", "QnnSystem.dll"]
        dlls_found = [dll for dll in qnn_dlls if shutil.which(dll) is not None]

        if ort_qnn_available:
            status = "Available (QNNExecutionProvider registered in ONNX Runtime)"
        elif dlls_found:
            status = f"QNN DLLs detected ({', '.join(dlls_found)}), but QNNExecutionProvider is not registered in ONNX Runtime"
        elif qnn_sdk_root:
            status = f"QNN_SDK_ROOT set ({qnn_sdk_root}), but runtime DLLs not registered in PATH"
        else:
            status = "Unavailable (requires Snapdragon ARM64 with Qualcomm QNN Execution Provider)"

        return {
            "providerAvailable": ort_qnn_available,
            "qnnSdkRoot": qnn_sdk_root,
            "dllsFound": dlls_found,
            "hasDllsInPath": len(dlls_found) > 0,
            "status": status
        }

    @staticmethod
    def get_snapdragon_status(arch_info: Dict[str, Any], cpu_info: Dict[str, Any], qnn_status: Dict[str, Any]) -> Dict[str, Any]:
        """
        Determines Snapdragon / Qualcomm NPU presence based strictly on verifiable evidence.
        ZERO fabrication: explicitly flags when running on x64 development machines.
        """
        is_arm64 = arch_info.get("isArm64", False)
        is_snapdragon_cpu = cpu_info.get("isSnapdragon", False)
        qnn_active = qnn_status.get("providerAvailable", False)

        if is_arm64 and is_snapdragon_cpu and qnn_active:
            status = "Snapdragon NPU detected & QNN Execution Provider active"
            detected = True
        elif is_arm64 and is_snapdragon_cpu:
            status = "Snapdragon ARM64 processor detected, but QNN Execution Provider not registered"
            detected = True
        elif is_arm64:
            status = "ARM64 architecture detected, but processor is not identified as Qualcomm Snapdragon"
            detected = False
        else:
            status = "Not detected (running on x64 development machine)"
            detected = False

        return {
            "detected": detected,
            "architectureMatch": is_arm64,
            "processorMatch": is_snapdragon_cpu,
            "npuAccelerated": qnn_active,
            "status": status
        }

    @classmethod
    def get_capabilities(cls) -> Dict[str, Any]:
        """
        Assembles the complete, verified hardware capability report.
        Zero fabricated values.
        """
        os_info = cls.get_os_info()
        arch_info = cls.get_architecture()
        cpu_info = cls.get_cpu_info()
        mem_info = cls.get_memory_info()
        gpu_info = cls.get_gpu_info()
        ort_info = cls.get_onnxruntime_info()
        cuda_status = cls.get_cuda_status(gpu_info, ort_info)
        qnn_status = cls.get_qnn_status(ort_info)
        snapdragon_status = cls.get_snapdragon_status(arch_info, cpu_info, qnn_status)

        # Truthful Device Classification
        if snapdragon_status.get("detected"):
            device_type = "Snapdragon AI PC"
        elif arch_info.get("isX64"):
            device_type = "Development Environment — x64"
        elif arch_info.get("isArm64"):
            device_type = "ARM64 Device (Non-Snapdragon)"
        else:
            device_type = f"Generic Host ({arch_info.get('raw')})"

        return {
            "deviceType": device_type,
            "architecture": arch_info.get("normalized"),
            "os": os_info,
            "cpu": cpu_info,
            "memory": mem_info,
            "gpu": gpu_info,
            "onnxruntime": ort_info,
            "accelerators": {
                "cuda": cuda_status,
                "qnn": qnn_status,
                "snapdragonNpu": snapdragon_status
            }
        }
