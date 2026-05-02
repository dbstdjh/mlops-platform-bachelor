package main

import (
	"os"
	"strconv"
	"strings"
	"time"
)

type Config struct {
	ListenAddr             string
	DatabaseURL            string
	SecretKey              string
	RequestTimeout         time.Duration
	MaxBodyBytes           int64
	CORSAllowedOriginRegex string
}

func LoadConfig() Config {
	return Config{
		ListenAddr:             getenv("LISTEN_ADDR", ":8080"),
		DatabaseURL:            normalizeDatabaseURL(getenv("DATABASE_URL", "")),
		SecretKey:              getenv("SECRET_KEY", "super-secret-dev-key-change-in-prod"),
		RequestTimeout:         secondsEnv("REQUEST_TIMEOUT_SECONDS", 30),
		MaxBodyBytes:           int64Env("MAX_BODY_BYTES", 2<<20),
		CORSAllowedOriginRegex: getenv("CORS_ALLOWED_ORIGIN_REGEX", `^https?://([a-z0-9-]+\.)?mldlc\.local(:\d+)?$`),
	}
}

func getenv(key string, fallback string) string {
	value := strings.TrimSpace(os.Getenv(key))
	if value == "" {
		return fallback
	}
	return value
}

func secondsEnv(key string, fallback int) time.Duration {
	value, err := strconv.Atoi(getenv(key, strconv.Itoa(fallback)))
	if err != nil || value <= 0 {
		value = fallback
	}
	return time.Duration(value) * time.Second
}

func int64Env(key string, fallback int64) int64 {
	value, err := strconv.ParseInt(getenv(key, strconv.FormatInt(fallback, 10)), 10, 64)
	if err != nil || value <= 0 {
		return fallback
	}
	return value
}

func normalizeDatabaseURL(value string) string {
	return strings.Replace(value, "postgresql+asyncpg://", "postgresql://", 1)
}
