# Build from the repo root so go.mod and internal/ are in the context:
#   docker build -f api-server/Dockerfile -t api-server .
FROM golang:1.27.3 AS build
WORKDIR /src
COPY go.mod go.sum ./
RUN go mod download
COPY . .
RUN CGO_ENABLED=0 go build -trimpath -o /out/api-server ./api-server

FROM gcr.io/distroless/static-debian12:nonroot
COPY --from=build /out/api-server /api-server
EXPOSE 8080
ENTRYPOINT ["/api-server"]
