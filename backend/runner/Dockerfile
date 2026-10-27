FROM python:3.12-slim
WORKDIR /runner
COPY entrypoint.py /runner/entrypoint.py
USER 65534:65534
ENTRYPOINT ["python", "-I", "-B", "/runner/entrypoint.py"]
