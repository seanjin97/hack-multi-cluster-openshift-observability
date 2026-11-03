IMAGE ?= api-server:dev

.PHONY: api-dev test lint build docker

api-dev:
	go tool air -c .air.toml

test:
	go test -race ./...

lint:
	go vet ./...
	@test -z "$$(gofmt -l .)" || { echo "gofmt needed:"; gofmt -l .; exit 1; }

build:
	CGO_ENABLED=0 go build -trimpath -o bin/api-server ./api-server

docker:
	docker build -f api-server/Dockerfile -t $(IMAGE) .
