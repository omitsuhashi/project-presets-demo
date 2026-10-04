FROM python:3.12.14-slim-bookworm@sha256:392307d22300de8b5986851a12d9176dfc0fc073e65bf6523ebd7dcbeb23564e
RUN pip install --no-cache-dir uv==0.11.7
WORKDIR /app
COPY . .
RUN uv sync --locked --no-dev --no-editable && chmod -R a+rX /app
ENV PATH="/app/.venv/bin:$PATH"
EXPOSE 8000
USER 65532:65532
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
