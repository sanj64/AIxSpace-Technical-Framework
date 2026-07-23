ARG PYTHON_BASE=python:3.11.15-slim-bookworm@sha256:b18992999dbe963a45a8a4da40ac2b1975be1a776d939d098c647482bcad5cba
FROM ${PYTHON_BASE} AS builder

ENV PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /build
COPY requirements-build.lock pyproject.toml README.md LICENSE-COMMERCIAL.md ./
COPY src ./src
RUN python -m pip install --no-cache-dir --require-hashes --requirement requirements-build.lock && \
    python -m pip wheel --no-deps --no-build-isolation --wheel-dir /wheels .

FROM ${PYTHON_BASE} AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    STREAMLIT_SERVER_ADDRESS=0.0.0.0 \
    STREAMLIT_SERVER_PORT=8501 \
    STREAMLIT_BROWSER_GATHER_USAGE_STATS=false

RUN groupadd --gid 10001 satish && useradd --uid 10001 --gid 10001 --no-create-home satish
WORKDIR /opt/satish
COPY requirements.lock ./
COPY --from=builder /wheels /wheels
COPY --from=builder /build/src/satish_commercial/app.py /opt/satish/app.py
RUN python -m pip install --no-cache-dir --require-hashes --requirement requirements.lock && \
    python -m pip install --no-cache-dir --no-deps /wheels/*.whl && \
    python -m pip uninstall --yes pip setuptools wheel && \
    rm -rf /wheels

USER 10001:10001
EXPOSE 8501
ENTRYPOINT ["python", "-m", "streamlit", "run", "/opt/satish/app.py"]
