IMAGE ?= worker-1:dev

.PHONY: dev test lint build docker

dev:
	go tool air -c .air.toml

test:
	go test -race ./...

lint:
	go vet ./...
	@test -z "$$(gofmt -l .)" || { echo "gofmt needed:"; gofmt -l .; exit 1; }

build:
	CGO_ENABLED=0 go build -trimpath -o bin/worker-1 ./worker-1

docker:
	docker build -f worker-1/Dockerfile -t $(IMAGE) .
