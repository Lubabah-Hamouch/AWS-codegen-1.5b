# syntax=docker/dockerfile:1
# Lambda container: llama.cpp (pinned to the build used for the eval) + the Q4_K_M GGUF + the app, behind the
# AWS Lambda Web Adapter. Build context is backend/. Inputs that are not in git:
#   vendor/src-b11856.tar.gz  llama.cpp source, sha256 checked below
#   model/model.gguf          the Q4_K_M model
# Build:  docker buildx build --platform linux/arm64 -t codegen-backend backend   (x86 for local spikes: linux/amd64)

FROM public.ecr.aws/lambda/provided:al2023 AS build
ARG TARGETARCH
ARG LLAMA_SHA256=504b268e4ee3eabadfef334bfd14e32956713bd0a95818e8a62431cb1c5e2dc4
RUN dnf install -y gcc gcc-c++ cmake make tar gzip findutils && dnf clean all
COPY vendor/src-b11856.tar.gz /tmp/llama.tar.gz
RUN echo "${LLAMA_SHA256}  /tmp/llama.tar.gz" | sha256sum -c - \
 && mkdir /src && tar -xzf /tmp/llama.tar.gz -C /src --strip-components=1
WORKDIR /src
# GGML_NATIVE=OFF: never bake in the build host's instruction set. Lambda arm64 is Graviton2 (Neoverse N1:
# dotprod + fp16, no i8mm/SVE). The x86 branch exists only for local spikes.
RUN if [ "$TARGETARCH" = "arm64" ]; then ARCHFLAGS="-mcpu=neoverse-n1"; else ARCHFLAGS="-mavx2 -mfma -mf16c"; fi \
 && cmake -B build -DCMAKE_BUILD_TYPE=Release -DGGML_NATIVE=OFF -DGGML_OPENMP=ON \
      -DBUILD_SHARED_LIBS=OFF -DLLAMA_CURL=OFF -DLLAMA_BUILD_TESTS=OFF -DLLAMA_BUILD_EXAMPLES=OFF \
      -DLLAMA_BUILD_SERVER=ON -DCMAKE_C_FLAGS="$ARCHFLAGS" -DCMAKE_CXX_FLAGS="$ARCHFLAGS" \
 && cmake --build build --target llama-server -j"$(nproc)" \
 && strip build/bin/llama-server

FROM public.ecr.aws/lambda/provided:al2023
# The OpenMP runtime comes from the distro package, not from a borrowed file.
RUN dnf install -y libgomp python3.12 && dnf clean all
COPY --from=build /src/build/bin/llama-server /opt/llama/llama-server
# Build gate: fail the image if the server has an unresolved shared library.
RUN ! ldd /opt/llama/llama-server | grep "not found" && ldd /opt/llama/llama-server
COPY --from=public.ecr.aws/awsguru/aws-lambda-adapter:0.9.1 /lambda-adapter /opt/extensions/lambda-adapter
COPY model/model.gguf /opt/model/model.gguf
COPY app /app
ENV PORT=8080 AWS_LWA_PORT=8080 AWS_LWA_READINESS_CHECK_PATH=/health \
    LLAMA_BIN=/opt/llama/llama-server MODEL_PATH=/opt/model/model.gguf
# The Web Adapter is the Lambda runtime; the image's own entrypoint (RIC/bootstrap) must not start.
ENTRYPOINT []
CMD ["python3.12", "/app/main.py"]
