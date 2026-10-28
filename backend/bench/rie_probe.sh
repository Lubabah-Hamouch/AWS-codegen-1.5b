#!/bin/bash
# Level 2 probe: run the image under the Lambda Runtime Interface Emulator and invoke it with a Function URL event.
# RIE listens on 8080 itself, so the app and the Web Adapter move to 8090.
export MSYS_NO_PATHCONV=1
IMG=${1:-codegen-backend:x86}
docker rm -f codegen-rie >/dev/null 2>&1
T0=$(date +%s.%N)
docker run -d --name codegen-rie --cpus 2 --memory 3g -p 9100:8080 -e PORT=8090 -e AWS_LWA_PORT=8090 -e LLAMA_THREADS=2 \
  --entrypoint /usr/local/bin/aws-lambda-rie "$IMG" python3.12 /app/main.py >/dev/null
EVENT='{"version":"2.0","routeKey":"$default","rawPath":"/health","rawQueryString":"","headers":{"host":"x.lambda-url.us-east-1.on.aws"},"requestContext":{"http":{"method":"GET","path":"/health","sourceIp":"1.2.3.4"}},"isBase64Encoded":false}'
until curl -s -o /dev/null -m 1 http://127.0.0.1:9100/ 2>/dev/null || [ "$(docker inspect -f '{{.State.Running}}' codegen-rie)" != true ]; do sleep 0.3; done
echo "invoking /health via RIE"
curl -s -m 120 -w "\nhttp=%{http_code} total=%{time_total}s\n" -XPOST http://127.0.0.1:9100/2015-03-31/functions/function/invocations -d "$EVENT"
echo "elapsed since docker run: $(( $(date +%s) - ${T0%.*} ))s"
docker logs codegen-rie 2>&1 | grep -v "I slot\|I srv\|I load\|I llama\|I common\|I main\|^$" | tail -25
docker rm -f codegen-rie >/dev/null 2>&1
echo done
