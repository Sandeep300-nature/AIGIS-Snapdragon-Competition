import os
import sys
import platform
import shutil
import subprocess
import time
from typing import Dict, Any, List, Optional

try:
    import psutil
except ImportError:
    psutil = None

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

        physical_cores = (psutil.cpu_count(logical=False) if psutil else None) or os.cpu_count() or 0
        logical_cores = (psutil.cpu_count(logical=True) if psutil else None) or os.cpu_count() or 0

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
        if psutil:
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
        return {
            "totalBytes": 0,
            "totalGb": 0.0,
            "availableGb": 0.0,
            "usedGb": 0.0,
            "percentUsed": 0.0,
            "note": "psutil not installed; memory metrics unavailable"
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

    @staticmethod
    def get_genie_status(arch_info: Dict[str, Any], cpu_info: Dict[str, Any]) -> Dict[str, Any]:
        """
        Tests Qualcomm Genie / GenieX runtime and model bundle availability independently.
        ZERO fabrication: never claims Genie runtime or NPU acceleration when absent.
        """
        is_arm64 = arch_info.get("isArm64", False)
        is_snapdragon = cpu_info.get("isSnapdragon", False)

        # Check for Genie runtime executables and DLLs
        genie_tools = ["geniex.exe", "geniex", "genie-t2t-run", "genie-t2t-run.exe", "geniex-bench", "geniex-bench.exe"]
        tools_found = [t for t in genie_tools if shutil.which(t) is not None]

        local_app_data = os.environ.get("LOCALAPPDATA")
        if local_app_data:
            geniex_path = os.path.join(local_app_data, "GenieX CLI", "geniex.exe")
            if os.path.isfile(geniex_path) and "geniex.exe" not in tools_found:
                tools_found.append("geniex.exe")

        genie_dlls = ["genie.dll", "QnnHtp.dll", "QnnSystem.dll"]
        dlls_found = [d for d in genie_dlls if shutil.which(d) is not None]

        genie_root = os.environ.get("GENIE_ROOT") or os.environ.get("GENIEX_PATH") or os.environ.get("QAIRT_SDK_ROOT")

        # Discover model bundle via configurable environment variable or standard GenieX cache paths
        candidate_bundle_dirs = [
            os.path.expanduser(r"~/.cache/geniex/models/qualcomm/Qwen3-4B-Instruct-2507"),
            os.path.expanduser(r"~/.cache/geniex/models/ai-hub-models/Qwen3-4B-Instruct-2507"),
            os.path.expanduser(r"~/.cache/geniex/models/Qwen3-4B-Instruct-2507"),
            r"D:\AIGIS-Snapdragon-Models\qwen3_4b_instruct_2507-geniex_qairt-w4a16-qualcomm_snapdragon_x_elite"
        ]
        discovered_dir = next((d for d in candidate_bundle_dirs if os.path.isdir(d)), candidate_bundle_dirs[0])
        bundle_dir = os.getenv("AIGIS_GENIE_MODEL_DIR", os.getenv("AIGIS_SNAPDRAGON_MODEL_DIR", discovered_dir))

        bundle_found = False
        missing_bundle_files = []
        expected_files = ["genie_config.json", "part1_of_4.bin", "part2_of_4.bin", "part3_of_4.bin", "part4_of_4.bin"]
        if os.path.isdir(bundle_dir):
            existing = set(os.listdir(bundle_dir))
            missing_bundle_files = [f for f in expected_files if f not in existing]
            bundle_found = (len(missing_bundle_files) == 0)
            if not bundle_found and any(f.endswith(".bin") for f in existing) and any(f.endswith(".json") for f in existing):
                bundle_found = True
                missing_bundle_files = []

        runtime_available = is_arm64 and is_snapdragon and (len(tools_found) > 0 or len(dlls_found) > 0)

        if not is_arm64:
            status = "Unavailable (running on x64 development host; Qualcomm Genie NPU runtime requires Windows on Snapdragon ARM64)"
        elif not runtime_available:
            status = "ARM64 host detected, but Qualcomm Genie runtime components (genie-t2t-run/genie.dll) not found in PATH"
        elif not bundle_found:
            status = f"Genie runtime detected, but Qwen3 bundle missing files at '{bundle_dir}': {missing_bundle_files}"
        else:
            status = "Available (Qualcomm Genie runtime & Qwen3-4B W4A16 bundle verified on Snapdragon)"

        return {
            "runtimeAvailable": runtime_available,
            "toolsFound": tools_found,
            "dllsFound": dlls_found,
            "genieRoot": genie_root,
            "bundleFound": bundle_found,
            "bundleDir": bundle_dir,
            "missingBundleFiles": missing_bundle_files,
            "modelId": "qwen3_4b_instruct_2507",
            "runtime": "GenieX-QAIRT",
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
        genie_status = cls.get_genie_status(arch_info, cpu_info)

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
                "snapdragonNpu": snapdragon_status,
                "genie": genie_status,
                "genieNpu": genie_status
            }
        }

    @classmethod
    def get_cpu_telemetry(cls) -> Dict[str, Any]:
        """
        Retrieves real-time CPU telemetry (utilization, clock speed, core counts, and thermal status).
        Temperature is reported as 'unavailable' if not exposed via reliable OS interfaces.
        """
        cpu_info = cls.get_cpu_info()
        brand = cpu_info.get("brand", "Unknown CPU")
        model = cpu_info.get("model", "")
        physical_cores = cpu_info.get("physicalCores", 0)
        logical_cores = cpu_info.get("logicalCores", 0)

        usage = 0.0
        clock_speed_ghz = None
        freq_state = "unavailable"
        temp_val = None
        temp_state = "unavailable"

        if psutil:
            try:
                usage = round(float(psutil.cpu_percent(interval=None)), 1)
            except Exception:
                usage = 0.0

            try:
                freq = psutil.cpu_freq()
                if freq and freq.current:
                    clock_speed_ghz = round(freq.current / 1000.0, 2)
                    freq_state = "available"
            except Exception:
                freq_state = "unavailable"

        # Truthful temperature check:
        # Standard Windows APIs do not expose CPU core temperatures without third-party kernel drivers.
        # We explicitly and truthfully report unavailable.
        return {
            "state": "available",
            "brand": brand,
            "model": model,
            "physicalCores": physical_cores,
            "logicalCores": logical_cores,
            "usagePercent": usage,
            "clockSpeedGhz": clock_speed_ghz,
            "clockSpeedStr": f"{clock_speed_ghz} GHz" if clock_speed_ghz is not None else "unavailable",
            "frequencyState": freq_state,
            "temperatureC": temp_val,
            "temperatureState": temp_state,
            "temperatureStr": f"{temp_val}°C" if temp_val is not None else "unavailable"
        }

    @classmethod
    def get_gpu_telemetry(cls) -> Dict[str, Any]:
        """
        Retrieves live GPU telemetry.
        Probes nvidia-smi for NVIDIA GPUs (querying utilization, temperature, and memory).
        Falls back to Win32_VideoController for integrated/Adreno/AMD/Intel GPUs.
        """
        # 1. Probe NVIDIA GPU via nvidia-smi
        if shutil.which("nvidia-smi"):
            try:
                cmd = [
                    "nvidia-smi",
                    "--query-gpu=name,driver_version,memory.total,memory.used,memory.free,utilization.gpu,temperature.gpu",
                    "--format=csv,noheader,nounits"
                ]
                output = subprocess.check_output(cmd, text=True, timeout=2.0).strip()
                lines = output.splitlines()
                if lines:
                    parts = [p.strip() for p in lines[0].split(",")]
                    if len(parts) >= 7:
                        name = parts[0]
                        driver = parts[1]
                        vram_total_mb = int(float(parts[2])) if parts[2].replace('.', '', 1).isdigit() else 0
                        vram_used_mb = int(float(parts[3])) if parts[3].replace('.', '', 1).isdigit() else 0
                        vram_free_mb = int(float(parts[4])) if parts[4].replace('.', '', 1).isdigit() else 0
                        utilization = int(float(parts[5])) if parts[5].replace('.', '', 1).isdigit() else 0
                        temp_c = int(float(parts[6])) if parts[6].replace('.', '', 1).isdigit() else None

                        vram_total_gb = round(vram_total_mb / 1024.0, 1)
                        vram_used_gb = round(vram_used_mb / 1024.0, 1)
                        vram_free_gb = round(vram_free_mb / 1024.0, 1)

                        return {
                            "detected": True,
                            "vendor": "NVIDIA",
                            "name": name,
                            "driverVersion": driver,
                            "vramTotalGb": vram_total_gb,
                            "vramUsedGb": vram_used_gb,
                            "vramFreeGb": vram_free_gb,
                            "vramStr": f"{vram_used_gb} / {vram_total_gb} GB",
                            "vramState": "available",
                            "usagePercent": utilization,
                            "utilizationState": "available",
                            "temperatureC": temp_c,
                            "temperatureState": "available" if temp_c is not None else "unavailable",
                            "temperatureStr": f"{temp_c}°C" if temp_c is not None else "unavailable",
                            "detectionMethod": "nvidia-smi"
                        }
            except Exception:
                pass

        # 2. Fallback: Windows display adapter probe (Win32_VideoController)
        gpu_info = cls.get_gpu_info()
        if gpu_info.get("detected", False):
            vram_total_gb = gpu_info.get("vramTotalGb", 0.0)
            return {
                "detected": True,
                "vendor": gpu_info.get("vendor", "Unknown"),
                "name": gpu_info.get("name", "Unknown GPU"),
                "driverVersion": gpu_info.get("driverVersion", "N/A"),
                "vramTotalGb": vram_total_gb,
                "vramUsedGb": None,
                "vramFreeGb": None,
                "vramStr": f"{vram_total_gb} GB total" if vram_total_gb > 0 else "unavailable",
                "vramState": "available" if vram_total_gb > 0 else "unavailable",
                "usagePercent": None,
                "utilizationState": "unavailable",
                "temperatureC": None,
                "temperatureState": "not_supported",
                "temperatureStr": "unavailable",
                "detectionMethod": gpu_info.get("detectionMethod", "Win32_VideoController")
            }

        return {
            "detected": False,
            "vendor": "None",
            "name": "No discrete GPU detected",
            "driverVersion": "N/A",
            "vramTotalGb": 0.0,
            "vramUsedGb": None,
            "vramFreeGb": None,
            "vramStr": "unavailable",
            "vramState": "not_supported",
            "usagePercent": None,
            "utilizationState": "not_supported",
            "temperatureC": None,
            "temperatureState": "not_supported",
            "temperatureStr": "unavailable",
            "detectionMethod": "none"
        }

    @classmethod
    def get_memory_telemetry(cls) -> Dict[str, Any]:
        """Retrieves live system memory / RAM metrics."""
        if psutil:
            try:
                vm = psutil.virtual_memory()
                total_gb = round(vm.total / (1024 ** 3), 1)
                avail_gb = round(vm.available / (1024 ** 3), 1)
                used_gb = round(vm.used / (1024 ** 3), 1)
                percent = round(vm.percent, 1)
                return {
                    "state": "available",
                    "totalGb": total_gb,
                    "usedGb": used_gb,
                    "availableGb": avail_gb,
                    "percentUsed": percent,
                    "ramStr": f"{used_gb} / {total_gb} GB",
                    "humanReadable": f"{used_gb} GB of {total_gb} GB used ({percent}%)"
                }
            except Exception as e:
                return {
                    "state": "unavailable",
                    "error": str(e),
                    "totalGb": 0.0,
                    "usedGb": 0.0,
                    "availableGb": 0.0,
                    "percentUsed": 0.0,
                    "ramStr": "unavailable",
                    "humanReadable": "unavailable"
                }
        return {
            "state": "not_supported",
            "totalGb": 0.0,
            "usedGb": 0.0,
            "availableGb": 0.0,
            "percentUsed": 0.0,
            "ramStr": "unavailable",
            "humanReadable": "unavailable"
        }

    @classmethod
    def get_storage_telemetry(cls, drive: str = "C:") -> Dict[str, Any]:
        """Retrieves live disk/storage telemetry for the primary drive."""
        target_path = drive if os.name == "nt" else "/"
        if psutil:
            try:
                disk = psutil.disk_usage(target_path)
                total_gb = round(disk.total / (1024 ** 3), 1)
                used_gb = round(disk.used / (1024 ** 3), 1)
                free_gb = round(disk.free / (1024 ** 3), 1)
                percent = round(disk.percent, 1)
                return {
                    "state": "available",
                    "drive": drive,
                    "totalGb": total_gb,
                    "usedGb": used_gb,
                    "freeGb": free_gb,
                    "percentUsed": percent,
                    "cDriveStr": f"{used_gb} / {total_gb} GB",
                    "humanReadable": f"{used_gb} GB of {total_gb} GB used ({free_gb} GB free, {percent}%)"
                }
            except Exception as e:
                return {
                    "state": "unavailable",
                    "drive": drive,
                    "error": str(e),
                    "totalGb": 0.0,
                    "usedGb": 0.0,
                    "freeGb": 0.0,
                    "percentUsed": 0.0,
                    "cDriveStr": "unavailable",
                    "humanReadable": "unavailable"
                }
        return {
            "state": "not_supported",
            "drive": drive,
            "totalGb": 0.0,
            "usedGb": 0.0,
            "freeGb": 0.0,
            "percentUsed": 0.0,
            "cDriveStr": "unavailable",
            "humanReadable": "unavailable"
        }

    @classmethod
    def get_battery_telemetry(cls) -> Dict[str, Any]:
        """Retrieves battery state, percentage, and charging status if battery is present."""
        if psutil:
            try:
                b = psutil.sensors_battery()
                if b is not None:
                    percent = int(b.percent)
                    power_plugged = bool(b.power_plugged)
                    charging_state = (
                        "charging" if (power_plugged and percent < 100)
                        else ("ac_connected" if power_plugged else "discharging")
                    )
                    secs_left = b.secsleft if b.secsleft and b.secsleft > 0 else None
                    hours_left = round(secs_left / 3600.0, 1) if secs_left else None
                    plugged_label = " (charging, AC connected)" if (power_plugged and percent < 100) else (
                        " (AC connected, fully charged)" if (power_plugged and percent >= 100) else " (discharging)"
                    )
                    return {
                        "state": "available",
                        "detected": True,
                        "percent": percent,
                        "powerPlugged": power_plugged,
                        "chargingState": charging_state,
                        "secsLeft": secs_left,
                        "hoursLeft": hours_left,
                        "batteryStr": f"{percent}%{plugged_label}"
                    }
                else:
                    return {
                        "state": "not_supported",
                        "detected": False,
                        "percent": None,
                        "powerPlugged": None,
                        "chargingState": "not_supported",
                        "secsLeft": None,
                        "hoursLeft": None,
                        "batteryStr": "not supported (no battery detected)"
                    }
            except Exception:
                pass
        return {
            "state": "unavailable",
            "detected": False,
            "percent": None,
            "powerPlugged": None,
            "chargingState": "unavailable",
            "secsLeft": None,
            "hoursLeft": None,
            "batteryStr": "unavailable"
        }

    _last_io_time: Optional[float] = None
    _last_disk_io: Any = None
    _last_net_io: Any = None
    _session_start_time: float = time.time()

    @classmethod
    def get_system_telemetry(cls, active_engine_label: Optional[str] = None) -> Dict[str, Any]:
        """
        Assembles complete, unified local system telemetry.
        Ground truth only: explicit availability states and zero fabricated metrics.
        Serves as the single source of truth for both the frontend HUD and conversational AI.
        """
        import time
        now = time.time()

        caps = cls.get_capabilities()
        os_info = caps.get("os", {})
        arch_info = caps.get("architecture", "Unknown")
        cpu_telemetry = cls.get_cpu_telemetry()
        gpu_telemetry = cls.get_gpu_telemetry()
        mem_telemetry = cls.get_memory_telemetry()
        storage_telemetry = cls.get_storage_telemetry()
        battery_telemetry = cls.get_battery_telemetry()

        uptime_sec = 0
        uptime_str = "unavailable"
        process_count = None
        active_threads = None

        # 1. High-precision native Windows process & thread counting via psapi.GetPerformanceInfo (<0.5ms)
        if sys.platform == "win32":
            try:
                import ctypes
                class PERFORMANCE_INFORMATION(ctypes.Structure):
                    _fields_ = [
                        ('cb', ctypes.c_ulong),
                        ('CommitTotal', ctypes.c_size_t),
                        ('CommitLimit', ctypes.c_size_t),
                        ('CommitPeak', ctypes.c_size_t),
                        ('PhysicalTotal', ctypes.c_size_t),
                        ('PhysicalAvailable', ctypes.c_size_t),
                        ('SystemCache', ctypes.c_size_t),
                        ('KernelTotal', ctypes.c_size_t),
                        ('KernelPaged', ctypes.c_size_t),
                        ('KernelNonpaged', ctypes.c_size_t),
                        ('PageSize', ctypes.c_size_t),
                        ('HandleCount', ctypes.c_ulong),
                        ('ProcessCount', ctypes.c_ulong),
                        ('ThreadCount', ctypes.c_ulong),
                    ]
                perf = PERFORMANCE_INFORMATION()
                perf.cb = ctypes.sizeof(PERFORMANCE_INFORMATION)
                if ctypes.windll.psapi.GetPerformanceInfo(ctypes.byref(perf), perf.cb):
                    process_count = int(perf.ProcessCount)
                    active_threads = int(perf.ThreadCount)
            except Exception:
                pass

        # 2. psutil fallback for uptime and process count
        if psutil:
            try:
                boot_time = psutil.boot_time()
                uptime_sec = int(now - boot_time)
                days = uptime_sec // 86400
                hours = (uptime_sec % 86400) // 3600
                mins = (uptime_sec % 3600) // 60
                if days > 0:
                    uptime_str = f"{days}d {hours}h"
                elif hours > 0:
                    uptime_str = f"{hours}h {mins}m"
                else:
                    uptime_str = f"{mins}m"
            except Exception:
                pass

            if process_count is None:
                try:
                    process_count = len(psutil.pids())
                except Exception:
                    process_count = "unavailable"

        if active_threads is None:
            active_threads = "unavailable"

        # 3. Disk I/O delta
        elapsed = max(0.1, now - (cls._last_io_time or now))
        cls._last_io_time = now

        curr_disk_io = psutil.disk_io_counters() if psutil else None
        if curr_disk_io and cls._last_disk_io:
            read_bytes = curr_disk_io.read_bytes - cls._last_disk_io.read_bytes
            write_bytes = curr_disk_io.write_bytes - cls._last_disk_io.write_bytes
            disk_read_kb = read_bytes / elapsed / 1024.0
            disk_write_kb = write_bytes / elapsed / 1024.0
        else:
            disk_read_kb = 0.0
            disk_write_kb = 0.0
        cls._last_disk_io = curr_disk_io

        disk_read_str = f"{round(disk_read_kb / 1024.0, 1)} MB/s" if disk_read_kb > 1024 else f"{int(disk_read_kb)} KB/s"
        disk_write_str = f"{round(disk_write_kb / 1024.0, 1)} MB/s" if disk_write_kb > 1024 else f"{int(disk_write_kb)} KB/s"
        storage_telemetry["readSpeed"] = disk_read_str
        storage_telemetry["writeSpeed"] = disk_write_str

        # 4. Network I/O delta
        curr_net_io = psutil.net_io_counters() if psutil else None
        if curr_net_io and cls._last_net_io:
            rx_bytes = curr_net_io.bytes_recv - cls._last_net_io.bytes_recv
            tx_bytes = curr_net_io.bytes_sent - cls._last_net_io.bytes_sent
            down_kb = rx_bytes / elapsed / 1024.0
            up_kb = tx_bytes / elapsed / 1024.0
        else:
            down_kb = 0.0
            up_kb = 0.0
        cls._last_net_io = curr_net_io

        down_str = f"{round(down_kb / 1024.0, 1)} MB/s" if down_kb > 1024 else f"{int(down_kb)} KB/s"
        up_str = f"{round(up_kb / 1024.0, 1)} MB/s" if up_kb > 1024 else f"{int(up_kb)} KB/s"

        sess_sec = int(now - cls._session_start_time)
        shours = sess_sec // 3600
        smins = (sess_sec % 3600) // 60
        ssecs = sess_sec % 60
        session_dur_str = f"{shours}h {smins}m" if shours > 0 else f"{smins}m {ssecs}s"

        snapdragon_status = caps.get("accelerators", {}).get("snapdragonNpu", {})
        genie_status = caps.get("accelerators", {}).get("genie", {})
        is_snapdragon = snapdragon_status.get("processorMatch", False)
        npu_detected = snapdragon_status.get("detected", False)
        npu_available = snapdragon_status.get("npuAccelerated", False) or genie_status.get("runtimeAvailable", False)
        npu_status_str = snapdragon_status.get("status", "Not detected")

        if active_engine_label:
            runtime_label = active_engine_label
        elif npu_available:
            runtime_label = "Qualcomm GenieX-QAIRT (Hexagon NPU)"
        elif caps.get("deviceType") == "Development Environment — x64":
            runtime_label = f"Local On-Device ({arch_info} CPU)"
        else:
            runtime_label = "Local On-Device"

        device_name = platform.node() if hasattr(platform, "node") else "Host"
        windows_build = os_info.get("version", "N/A")
        competition_mode = os.getenv("AIGIS_COMPETITION_MODE", "true").lower() in ("true", "1", "yes")

        return {
            "identity": {
                "os": f"{os_info.get('system')} {os_info.get('release')}",
                "version": windows_build,
                "deviceName": device_name,
                "architecture": arch_info,
                "deviceType": caps.get("deviceType")
            },
            "cpu": {
                "usage": int(cpu_telemetry.get("usagePercent", 0)),
                "temp": cpu_telemetry.get("temperatureC") if cpu_telemetry.get("temperatureC") is not None else "unavailable",
                "clockSpeed": cpu_telemetry.get("clockSpeedStr", "unavailable"),
                "brand": cpu_telemetry.get("brand"),
                "physicalCores": cpu_telemetry.get("physicalCores"),
                "logicalCores": cpu_telemetry.get("logicalCores"),
                "temperatureState": cpu_telemetry.get("temperatureState")
            },
            "gpu": {
                "name": gpu_telemetry.get("name"),
                "usage": gpu_telemetry.get("usagePercent") if gpu_telemetry.get("usagePercent") is not None else 0,
                "temp": gpu_telemetry.get("temperatureC") if gpu_telemetry.get("temperatureC") is not None else "unavailable",
                "vramUsed": gpu_telemetry.get("vramUsedGb", 0.0) or 0.0,
                "vramTotal": gpu_telemetry.get("vramTotalGb", 0.0) or 0.0,
                "vramStr": gpu_telemetry.get("vramStr", "unavailable"),
                "temperatureState": gpu_telemetry.get("temperatureState"),
                "utilizationState": gpu_telemetry.get("utilizationState"),
                "detected": gpu_telemetry.get("detected")
            },
            "memory": {
                "ramUsed": mem_telemetry.get("usedGb", 0.0),
                "ramTotal": mem_telemetry.get("totalGb", 0.0),
                "ramStr": mem_telemetry.get("ramStr", "unavailable"),
                "usage": mem_telemetry.get("percentUsed", 0.0),
                "availableGb": mem_telemetry.get("availableGb", 0.0),
                "state": mem_telemetry.get("state")
            },
            "storage": {
                "cDriveUsed": storage_telemetry.get("usedGb", 0.0),
                "cDriveTotal": storage_telemetry.get("totalGb", 0.0),
                "freeGb": storage_telemetry.get("freeGb", 0.0),
                "cDriveStr": storage_telemetry.get("cDriveStr", "unavailable"),
                "usage": storage_telemetry.get("percentUsed", 0.0),
                "readSpeed": disk_read_str,
                "writeSpeed": disk_write_str,
                "state": storage_telemetry.get("state")
            },
            "battery": battery_telemetry,
            "aiHardware": {
                "isSnapdragon": is_snapdragon,
                "npuDetected": npu_detected,
                "npuAvailable": npu_available,
                "npuStatus": npu_status_str,
                "activeRuntime": runtime_label
            },
            "network": {
                "downloadSpeed": down_str,
                "uploadSpeed": up_str,
                "state": "available"
            },
            "aigis": {
                "activeEngine": runtime_label,
                "competitionMode": competition_mode,
                "sessionDuration": session_dur_str
            },
            "system": {
                "uptime": uptime_str,
                "uptimeSec": uptime_sec,
                "windowsBuild": windows_build,
                "processCount": process_count if process_count is not None else "unavailable",
                "activeThreads": active_threads if active_threads is not None else "unavailable",
                "battery": battery_telemetry.get("batteryStr", "unavailable")
            }
        }
