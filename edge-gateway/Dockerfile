FROM golang:1.22-alpine AS build

WORKDIR /src
COPY go.mod ./
RUN go mod download
COPY . .
RUN CGO_ENABLED=0 GOOS=linux go build -o /out/edge-gateway .

FROM alpine:3.21
WORKDIR /app
COPY --from=build /out/edge-gateway /app/edge-gateway
EXPOSE 8080
CMD ["/app/edge-gateway"]
