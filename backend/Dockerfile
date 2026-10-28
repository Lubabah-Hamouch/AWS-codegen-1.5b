# syntax=docker/dockerfile:1
# Lambda container: llama.cpp (pinned to the build used for the eval) + the Q4_K_M GGUF + the app, behind the AWS
# Lambda Web Adapter. Build context is backend/. Inputs that are not in git:
#   vendor/src-b11856.tar.gz  llama.cpp source, sha256 checked below
#   model/model.gguf          the Q4_K_M model
# Build + push: infra/scripts/build_push.ps1 -Dockerfile Dockerfile -Tag model-N   (linux/arm64)
#
# llama.cpp is CROSS-compiled on the build host (Debian bullseye, glibc 2.31, so the binary runs on AL2023's 2.34).
# Compiling under QEMU emulation would take hours; only the small final-stage steps (dnf, pip, ldd) run emulated.

FROM --platform=$BUILDPLATFORM debian:bullseye-slim AS build
ARG TARGETARCH
ARG LLAMA_SHA256=504b268e4ee3eabadfef334bfd14e32956713bd0a95818e8a62431cb1c5e2dc4
# bullseye is end-of-life: its packages now live only on archive.debian.org. glibc 2.31 is the point (see above).
RUN rm -f /etc/apt/sources.list.d/* \
 && printf 'deb http://archive.debian.org/debian bullseye main\ndeb http://archive.debian.org/debian-security bullseye-security main\n' > /etc/apt/sources.list \
 && apt-get -o Acquire::Check-Valid-Until=false update && apt-get install -y --no-install-recommends ca-certificates cmake make gcc g++ binutils \
      $( [ "$TARGETARCH" = "arm64" ] && echo gcc-aarch64-linux-gnu g++-aarch64-linux-gnu binutils-aarch64-linux-gnu ) \
 && rm -rf /var/lib/apt/lists/*
COPY vendor/src-b11856.tar.gz /tmp/llama.tar.gz
RUN echo "${LLAMA_SHA256}  /tmp/llama.tar.gz" | sha256sum -c - \
 && mkdir /src && tar -xzf /tmp/llama.tar.gz -C /src --strip-components=1
WORKDIR /src
# GGML_NATIVE=OFF: never bake in the build host's instruction set. Lambda arm64 is Graviton2 (Neoverse N1):
# armv8.2-a + dotprod + fp16, no i8mm/SVE. The amd64 branch exists only for local spikes.
RUN if [ "$TARGETARCH" = "arm64" ]; then \
      ARCH="-DCMAKE_SYSTEM_NAME=Linux -DCMAKE_SYSTEM_PROCESSOR=aarch64 -DCMAKE_C_COMPILER=aarch64-linux-gnu-gcc -DCMAKE_CXX_COMPILER=aarch64-linux-gnu-g++ -DGGML_CPU_ARM_ARCH=armv8.2-a+dotprod+fp16"; \
      OBJDUMP=aarch64-linux-gnu-objdump; READELF=aarch64-linux-gnu-readelf; \
    else ARCH="-DCMAKE_C_FLAGS=-mavx2\ -mfma\ -mf16c -DCMAKE_CXX_FLAGS=-mavx2\ -mfma\ -mf16c"; OBJDUMP=objdump; READELF=readelf; fi \
 && cmake -B build -DCMAKE_BUILD_TYPE=Release -DGGML_NATIVE=OFF -DGGML_OPENMP=ON -DBUILD_SHARED_LIBS=OFF \
      -DLLAMA_CURL=OFF -DLLAMA_BUILD_TESTS=OFF -DLLAMA_BUILD_EXAMPLES=OFF -DLLAMA_BUILD_SERVER=ON $ARCH \
 && cmake --build build --target llama-server -j"$(nproc)" \
 && cp build/bin/llama-server /llama-server \
 && ( [ "$TARGETARCH" = "arm64" ] && aarch64-linux-gnu-strip /llama-server || strip /llama-server ) \
 && $READELF -h /llama-server | grep -E "Machine|Class" \
 && echo "NEEDED:" && $READELF -d /llama-server | grep NEEDED \
 && echo "max GLIBC symbol version:" && $OBJDUMP -T /llama-server | grep -o "GLIBC_[0-9.]*" | sort -uV | tail -1

FROM public.ecr.aws/lambda/provided:al2023
# The OpenMP runtime comes from the distro package, not from a borrowed file.
RUN dnf install -y libgomp python3.12 python3.12-pip && dnf clean all \
 && python3.12 -m pip install --no-cache-dir boto3
COPY --from=build /llama-server /opt/llama/llama-server
# Build gate: fail the image if the server has an unresolved shared library.
RUN ! ldd /opt/llama/llama-server | grep "not found" && ldd /opt/llama/llama-server
COPY --from=public.ecr.aws/awsguru/aws-lambda-adapter:0.9.1 /lambda-adapter /opt/extensions/lambda-adapter
COPY model/model.gguf /opt/model/model.gguf
COPY app /app
ENV PORT=8080 AWS_LWA_PORT=8080 AWS_LWA_READINESS_CHECK_PATH=/health AWS_LWA_INVOKE_MODE=response_stream \
    LLAMA_BIN=/opt/llama/llama-server MODEL_PATH=/opt/model/model.gguf
# The Web Adapter is the Lambda runtime; the image's own entrypoint (RIC/bootstrap) must not start.
ENTRYPOINT []
CMD ["python3.12", "/app/main.py"]
