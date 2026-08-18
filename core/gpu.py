"""GPU auto-detection — shared by all video projects."""
import subprocess, os

def detect_gpu():
    """Detect available GPU and return capabilities dict. Cached after first call."""
    if hasattr(detect_gpu, "_cache"):
        return detect_gpu._cache

    caps = {
        "available": False,
        "name": "",
        "encoder_h264": "libx264",  # fallback
        "encoder_hevc": "libx265",  # fallback
        "decoder_h264": "",         # empty = software
        "whisper_device": "cpu",
        "whisper_compute": "int8",
        "hyperframes_gpu": "",
    }

    # Check NVIDIA GPU
    try:
        r = subprocess.run(["nvidia-smi", "--query-gpu=name,driver_version,memory.total",
                           "--format=csv,noheader"], capture_output=True, text=True, timeout=10)
        if r.returncode == 0 and r.stdout.strip():
            caps["available"] = True
            caps["name"] = r.stdout.strip().split(",")[0].strip()
            caps["whisper_device"] = "cuda"
            caps["whisper_compute"] = "float16"

            # Check NVENC availability
            try:
                r2 = subprocess.run(["ffmpeg", "-encoders"], capture_output=True, text=True, timeout=10)
                encoders = r2.stdout + r2.stderr
                if "h264_nvenc" in encoders:
                    caps["encoder_h264"] = "h264_nvenc"
                    caps["decoder_h264"] = "h264_cuvid"
                if "hevc_nvenc" in encoders:
                    caps["encoder_hevc"] = "hevc_nvenc"
            except:
                pass

            caps["hyperframes_gpu"] = "--gpu"
    except:
        pass

    # Fallback: check AMD
    if not caps["available"]:
        try:
            r = subprocess.run(["ffmpeg", "-encoders"], capture_output=True, text=True, timeout=10)
            if "h264_amf" in r.stdout + r.stderr:
                caps["available"] = True
                caps["encoder_h264"] = "h264_amf"
                caps["name"] = "AMD GPU (AMF)"
        except:
            pass

    detect_gpu._cache = caps
    return caps


def ffmpeg_encode_args(gpu_caps=None):
    """Return ffmpeg encoder arguments for the best available GPU."""
    caps = gpu_caps or detect_gpu()
    enc = caps["encoder_h264"]

    if enc == "h264_nvenc":
        return ["-c:v", "h264_nvenc", "-preset", "p4", "-tune", "hq", "-rc", "vbr", "-cq", "18",
                "-b:v", "0", "-r", "30", "-c:a", "aac", "-b:a", "128k"]
    elif enc == "h264_amf":
        return ["-c:v", "h264_amf", "-quality", "balanced", "-usage", "transcoding",
                "-r", "30", "-c:a", "aac", "-b:a", "128k"]
    else:
        return ["-c:v", "libx264", "-preset", "fast", "-crf", "18", "-r", "30", "-c:a", "aac", "-b:a", "128k"]


def status():
    """Print GPU detection status."""
    caps = detect_gpu()
    if caps["available"]:
        print(f"  GPU: {caps['name']} | encoder={caps['encoder_h264']} | whisper={caps['whisper_device']}")
    else:
        print("  GPU: none detected (using CPU)")
    return caps


if __name__ == "__main__":
    import json
    print(json.dumps(detect_gpu(), indent=2))
