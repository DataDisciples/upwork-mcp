# Stage 1: Build the Go bridge
# CGO is required by go-sqlite3 — we need gcc in the build stage
FROM golang:1.24-alpine AS builder

RUN apk add --no-cache gcc musl-dev

WORKDIR /build

# Cache deps separately from source
COPY go.mod go.sum ./
RUN go mod download

COPY . .
RUN CGO_ENABLED=1 GOOS=linux go build -o whatsapp-bridge .

# Stage 2: Lean runtime image
FROM alpine:latest

# ca-certificates: for HTTPS calls to WhatsApp servers
# ffmpeg: for converting audio to ogg/opus (voice messages)
RUN apk add --no-cache ca-certificates ffmpeg

WORKDIR /app
COPY --from=builder /build/whatsapp-bridge .

# WhatsApp session DB (whatsapp.db) and message DB (messages.db)
# live in ./store/ relative to the binary — mount a persistent
# Railway volume here so they survive redeploys
VOLUME ["/app/store"]

EXPOSE 8080

CMD ["./whatsapp-bridge"]
