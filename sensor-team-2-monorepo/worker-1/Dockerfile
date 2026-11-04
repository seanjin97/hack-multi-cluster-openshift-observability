# Build from the repo root so go.mod and internal/ are in the context:
#   docker build -f worker-1/Dockerfile -t worker-1 .
FROM golang:1.27.3 AS build
WORKDIR /src
COPY go.mod go.sum ./
RUN go mod download
COPY . .
RUN CGO_ENABLED=0 go build -trimpath -o /out/worker-1 ./worker-1

FROM gcr.io/distroless/static-debian12:nonroot
COPY --from=build /out/worker-1 /worker-1
EXPOSE 8080
ENTRYPOINT ["/worker-1"]
