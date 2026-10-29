"""No local execution fallback. The runner receives only normalized input and parameters."""
import json
import shutil
import subprocess
import tempfile
import threading
import time
from uuid import uuid4
from fastapi import HTTPException

IMAGE = "architecture-registry-python:2"
TIMEOUT = 30
OUTPUT_LIMIT = 1024 * 1024


def runtime_status(image=IMAGE):
    docker = shutil.which("docker")
    if not docker: return {"available": False, "message": "Docker не установлен"}
    try:
        inspect = subprocess.run([docker, "image", "inspect", image, "--format", "{{.Id}}"], capture_output=True, timeout=8, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        if inspect.returncode: return {"available": False, "message": "Docker недоступен или образ не собран. Запустите scripts/setup-python-runner.ps1"}
        return {"available": True, "image": image, "image_id": inspect.stdout.decode().strip(), "timeout": TIMEOUT}
    except (OSError, subprocess.TimeoutExpired): return {"available": False, "message": "Docker не отвечает"}


def run_python(code, document, params, *, expected_runtime=None, image=IMAGE, previous_results=None):
    state = runtime_status(expected_runtime or image)
    if not state["available"]: raise HTTPException(503, state["message"])
    payload = json.dumps({"code": code, "document": document, "params": params, "previous_results": previous_results or {"fields": {}, "steps": [], "conflicts": []}}, ensure_ascii=False, allow_nan=False).encode()
    if len(payload) > 16 * 1024 * 1024: raise HTTPException(422, "Вход Python превышает 16 MiB")
    name = "arch-step-" + uuid4().hex
    docker = shutil.which("docker")
    args = [docker, "run", "--rm", "--pull=never", "--name", name, "--network", "none", "--read-only",
            "--user", "65534:65534", "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
            "--memory", "512m", "--memory-swap", "512m", "--cpus", "1", "--pids-limit", "64",
            "--tmpfs", "/tmp:rw,noexec,nosuid,size=16m", "--log-driver", "none", "-i", state["image_id"]]
    output, errors, exceeded = bytearray(), bytearray(), threading.Event()

    def read(pipe, target):
        while chunk := pipe.read(8192):
            if len(target) + len(chunk) > OUTPUT_LIMIT: exceeded.set()
            if len(target) < OUTPUT_LIMIT: target.extend(chunk[:OUTPUT_LIMIT - len(target)])
        pipe.close()

    proc = None
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        with tempfile.TemporaryFile() as source:
            source.write(payload); source.seek(0)
            proc = subprocess.Popen(args, stdin=source, stdout=subprocess.PIPE, stderr=subprocess.PIPE, creationflags=flags)
            readers = [threading.Thread(target=read, args=(proc.stdout, output), daemon=True), threading.Thread(target=read, args=(proc.stderr, errors), daemon=True)]
            for thread in readers: thread.start()
            deadline = time.monotonic() + TIMEOUT
            while proc.poll() is None:
                if exceeded.is_set(): raise HTTPException(422, "Python превысил лимит вывода 1 MiB")
                if time.monotonic() >= deadline: raise HTTPException(422, f"Python превысил лимит времени {TIMEOUT} секунд")
                time.sleep(.05)
            for thread in readers: thread.join(timeout=2)
            if exceeded.is_set(): raise HTTPException(422, "Python превысил лимит вывода 1 MiB")
            if proc.returncode: raise HTTPException(422, "Python-шаг завершился ошибкой: проверьте код и лимиты контейнера")
            try:
                result = json.loads(output)
                if not isinstance(result, dict): raise ValueError()
                result["runtime_image_id"] = state["image_id"]
                return result
            except (ValueError, UnicodeDecodeError): raise HTTPException(422, "Python должен вернуть StepResult JSON через emit; не используйте print") from None
    except OSError: raise HTTPException(503, "Не удалось запустить Docker") from None
    finally:
        if proc and proc.poll() is None: proc.kill()
        try:
            subprocess.run([docker, "rm", "-f", name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=8, creationflags=flags)
        except (OSError, subprocess.TimeoutExpired): pass
        if proc:
            try: proc.wait(timeout=3)
            except subprocess.TimeoutExpired: pass
