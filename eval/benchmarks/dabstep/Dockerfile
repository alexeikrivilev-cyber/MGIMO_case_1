# DABstep stand (О4) — образ стенда. Стек: только stdlib python3
# (pandas намеренно не ставим: задачи решаются кодом модели, а не
# нашим; stdlib достаточно для CSV/JSON агрегаций этого масштаба).
FROM ubuntu:24.04

RUN apt-get update && apt-get install -y --no-install-recommends \
      python3 ca-certificates curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /workdir
COPY scripts/ /workdir/scripts/
COPY data/ /workdir/data/

ENV DABSTEP_MAX_STEPS=12
# STEPFUN_API_KEY передаётся из окружения хоста (--env), не в образ.

ENTRYPOINT ["python3", "/workdir/scripts/run.py"]
