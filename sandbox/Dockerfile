# Nodus kod calistirma sandbox'i.  Kurulum:  docker build -t nodus-sandbox sandbox
# Sonra .env icine:  NODUS_SANDBOX=docker
# Konteyner agsizdir (--network none), yalnizca workspace/ klasorunu gorur; API anahtarlari icine girmez.
FROM python:3.12-slim
RUN pip install --no-cache-dir numpy scipy sympy matplotlib pandas fluids CoolProp pint anastruct openpyxl
WORKDIR /work
