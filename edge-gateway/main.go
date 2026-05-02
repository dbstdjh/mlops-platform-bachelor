package main

import (
	"context"
	"log"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"time"
)

func main() {
	config := LoadConfig()
	ctx := context.Background()
	store, err := NewPostgresStore(ctx, config.DatabaseURL)
	if err != nil {
		log.Fatalf("connect database: %v", err)
	}
	defer store.Close()

	server := &http.Server{
		Addr:              config.ListenAddr,
		Handler:           NewServer(store, config).routes(),
		ReadHeaderTimeout: 5 * time.Second,
	}

	go func() {
		log.Printf("edge gateway listening on %s", config.ListenAddr)
		if err := server.ListenAndServe(); err != nil && err != http.ErrServerClosed {
			log.Fatalf("serve: %v", err)
		}
	}()

	stop := make(chan os.Signal, 1)
	signal.Notify(stop, syscall.SIGINT, syscall.SIGTERM)
	<-stop

	shutdownCtx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()
	if err := server.Shutdown(shutdownCtx); err != nil {
		log.Printf("shutdown: %v", err)
	}
}
