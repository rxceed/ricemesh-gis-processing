import subprocess
from pathlib import Path

# Upsclae the image using Real-ESRGAN by creating a subprocess of Real-ESRGAN binary executable
def upscale(src_img_path: str, output_img_path: str):
    ESRGAN_EXEC_PATH = Path.joinpath(Path.cwd(), "realesrgan/realesrgan-ncnn-vulkan").resolve()
    esrgan_args = ["-i", src_img_path, "-o", output_img_path]

    esrgan = subprocess.run([ESRGAN_EXEC_PATH, esrgan_args[0], esrgan_args[1], esrgan_args[2], esrgan_args[3]], capture_output=True, text=True, check=True)
    print("Output:", esrgan.stdout)
    print("Error:", esrgan.stderr)
    print("Exit code:", esrgan.returncode)