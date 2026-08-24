FROM python:3.12.10-slim-bookworm
WORKDIR /app
COPY requirements-runtime.txt pyproject.toml README.md LICENSE ./
RUN python -m pip install --no-cache-dir -r requirements-runtime.txt
COPY src ./src
RUN python -m pip install --no-cache-dir --no-deps .
USER 65532:65532
EXPOSE 8000
CMD ["python", "-m", "uvicorn", "industrial_reliability.api:create_app_from_env", "--factory", "--host", "0.0.0.0", "--port", "8000"]
