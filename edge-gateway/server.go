package main

import (
	"bytes"
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"regexp"
	"strings"
	"sync"
	"time"

	"github.com/golang-jwt/jwt/v5"
	"github.com/santhosh-tekuri/jsonschema/v5"
)

type Server struct {
	store          Store
	secretKey      []byte
	httpClient     *http.Client
	requestTimeout time.Duration
	maxBodyBytes   int64
	corsOrigin     *regexp.Regexp
	schemas        map[string]*jsonschema.Schema
	schemasMu      sync.RWMutex
}

func NewServer(store Store, config Config) *Server {
	corsOrigin, _ := regexp.Compile(config.CORSAllowedOriginRegex)
	return &Server{
		store:          store,
		secretKey:      []byte(config.SecretKey),
		httpClient:     &http.Client{Timeout: config.RequestTimeout},
		requestTimeout: config.RequestTimeout,
		maxBodyBytes:   config.MaxBodyBytes,
		corsOrigin:     corsOrigin,
		schemas:        make(map[string]*jsonschema.Schema),
	}
}

func (s *Server) routes() http.Handler {
	mux := http.NewServeMux()
	mux.HandleFunc("GET /health", s.health)
	mux.HandleFunc("GET /ready", s.ready)
	mux.HandleFunc("/api/v1/deployments/", s.predict)
	return s.withCORS(mux)
}

func (s *Server) withCORS(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		origin := r.Header.Get("Origin")
		if origin != "" && s.corsOrigin != nil && s.corsOrigin.MatchString(origin) {
			w.Header().Set("Access-Control-Allow-Origin", origin)
			w.Header().Set("Access-Control-Allow-Methods", "GET,POST,OPTIONS")
			w.Header().Set("Access-Control-Allow-Headers", "Authorization,Content-Type,Accept")
			w.Header().Set("Vary", "Origin")
		}
		if r.Method == http.MethodOptions {
			w.WriteHeader(http.StatusNoContent)
			return
		}
		next.ServeHTTP(w, r)
	})
}

func (s *Server) health(w http.ResponseWriter, _ *http.Request) {
	writeJSON(w, http.StatusOK, map[string]string{"status": "ok"})
}

func (s *Server) ready(w http.ResponseWriter, r *http.Request) {
	ctx, cancel := context.WithTimeout(r.Context(), 2*time.Second)
	defer cancel()
	if err := s.store.Ping(ctx); err != nil {
		writeJSON(w, http.StatusServiceUnavailable, map[string]string{"detail": "database unavailable"})
		return
	}
	writeJSON(w, http.StatusOK, map[string]string{"status": "ready"})
}

func (s *Server) predict(w http.ResponseWriter, r *http.Request) {
	start := time.Now()
	if r.Method != http.MethodPost {
		writeJSON(w, http.StatusMethodNotAllowed, map[string]string{"detail": "method not allowed"})
		return
	}
	slug, ok := deploymentSlug(r.URL.Path)
	if !ok {
		writeJSON(w, http.StatusNotFound, map[string]string{"detail": "not found"})
		return
	}
	userID, ok := s.authenticate(r)
	if !ok {
		writeJSON(w, http.StatusUnauthorized, map[string]string{"detail": "Unauthorized"})
		return
	}

	ctx, cancel := context.WithTimeout(r.Context(), s.requestTimeout)
	defer cancel()
	target, err := s.store.LookupDeployment(ctx, userID, slug)
	if errors.Is(err, ErrDeploymentNotFound) {
		writeJSON(w, http.StatusNotFound, map[string]string{"detail": "Deployment not found"})
		return
	}
	if err != nil {
		writeJSON(w, http.StatusInternalServerError, map[string]string{"detail": "Deployment lookup failed"})
		return
	}

	body, err := io.ReadAll(io.LimitReader(r.Body, s.maxBodyBytes+1))
	if err != nil {
		s.respondAndLog(ctx, w, target.ID, nil, map[string]string{"detail": "Request body could not be read"}, http.StatusBadRequest, start)
		return
	}
	if int64(len(body)) > s.maxBodyBytes {
		s.respondAndLog(ctx, w, target.ID, nil, map[string]string{"detail": "Request body is too large"}, http.StatusRequestEntityTooLarge, start)
		return
	}
	var payload any
	if err := json.Unmarshal(body, &payload); err != nil {
		s.respondAndLog(ctx, w, target.ID, nil, map[string]string{"detail": "Request body must be valid JSON"}, http.StatusBadRequest, start)
		return
	}
	if len(target.InputSchema) > 0 {
		if err := s.validate(target, payload); err != nil {
			s.respondAndLog(ctx, w, target.ID, payload, map[string]string{"detail": err.Error()}, http.StatusUnprocessableEntity, start)
			return
		}
	}

	statusCode, output, responseBody, contentType := s.proxy(ctx, target, body)
	s.logInference(ctx, target.ID, payload, output, statusCode, time.Since(start))
	if contentType == "" {
		contentType = "application/json"
	}
	w.Header().Set("Content-Type", contentType)
	w.WriteHeader(statusCode)
	_, _ = w.Write(responseBody)
}

func deploymentSlug(path string) (string, bool) {
	const prefix = "/api/v1/deployments/"
	const suffix = ":predict"
	if !strings.HasPrefix(path, prefix) || !strings.HasSuffix(path, suffix) {
		return "", false
	}
	slug := strings.TrimSuffix(strings.TrimPrefix(path, prefix), suffix)
	if slug == "" || strings.Contains(slug, "/") {
		return "", false
	}
	return slug, true
}

func (s *Server) authenticate(r *http.Request) (string, bool) {
	header := strings.TrimSpace(r.Header.Get("Authorization"))
	tokenText, ok := strings.CutPrefix(header, "Bearer ")
	if !ok || strings.TrimSpace(tokenText) == "" {
		return "", false
	}
	claims := jwt.MapClaims{}
	token, err := jwt.ParseWithClaims(
		tokenText,
		claims,
		func(token *jwt.Token) (any, error) {
			return s.secretKey, nil
		},
		jwt.WithValidMethods([]string{jwt.SigningMethodHS256.Alg()}),
	)
	if err != nil || token == nil || !token.Valid {
		return "", false
	}
	sub, ok := claims["sub"].(string)
	return sub, ok && sub != ""
}

func (s *Server) validate(target DeploymentTarget, payload any) error {
	schema, err := s.compiledSchema(target)
	if err != nil {
		return fmt.Errorf("deployment input schema is invalid: %w", err)
	}
	if err := schema.Validate(payload); err != nil {
		return err
	}
	return nil
}

func (s *Server) compiledSchema(target DeploymentTarget) (*jsonschema.Schema, error) {
	key := schemaCacheKey(target)
	s.schemasMu.RLock()
	schema := s.schemas[key]
	s.schemasMu.RUnlock()
	if schema != nil {
		return schema, nil
	}

	compiler := jsonschema.NewCompiler()
	if err := compiler.AddResource(key, bytes.NewReader(target.InputSchema)); err != nil {
		return nil, err
	}
	compiled, err := compiler.Compile(key)
	if err != nil {
		return nil, err
	}
	s.schemasMu.Lock()
	s.schemas[key] = compiled
	s.schemasMu.Unlock()
	return compiled, nil
}

func schemaCacheKey(target DeploymentTarget) string {
	sum := sha256.Sum256(target.InputSchema)
	return "schema-" + target.ID + "-" + hex.EncodeToString(sum[:]) + ".json"
}

func (s *Server) proxy(ctx context.Context, target DeploymentTarget, body []byte) (int, any, []byte, string) {
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, target.predictURL(), bytes.NewReader(body))
	if err != nil {
		return http.StatusInternalServerError, map[string]string{"detail": "Proxy request could not be built"}, []byte(`{"detail":"Proxy request could not be built"}`), "application/json"
	}
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("Accept", "application/json")

	response, err := s.httpClient.Do(req)
	if err != nil {
		return http.StatusBadGateway, map[string]string{"detail": "Model endpoint unavailable"}, []byte(`{"detail":"Model endpoint unavailable"}`), "application/json"
	}
	defer response.Body.Close()

	responseBody, err := io.ReadAll(io.LimitReader(response.Body, s.maxBodyBytes+1))
	if err != nil {
		return http.StatusBadGateway, map[string]string{"detail": "Model response could not be read"}, []byte(`{"detail":"Model response could not be read"}`), "application/json"
	}
	var output any
	if len(responseBody) > 0 {
		_ = json.Unmarshal(responseBody, &output)
	}
	return response.StatusCode, output, responseBody, response.Header.Get("Content-Type")
}

func (t DeploymentTarget) predictURL() string {
	if t.ProxyURL != "" {
		return t.ProxyURL
	}
	return fmt.Sprintf("http://%s.%s.svc.cluster.local:%d/predict", t.ServiceName, t.Namespace, t.ServicePort)
}

func (s *Server) respondAndLog(ctx context.Context, w http.ResponseWriter, deploymentID string, input any, output any, statusCode int, start time.Time) {
	s.logInference(ctx, deploymentID, input, output, statusCode, time.Since(start))
	writeJSON(w, statusCode, output)
}

func (s *Server) logInference(ctx context.Context, deploymentID string, input any, output any, statusCode int, latency time.Duration) {
	logCtx, cancel := context.WithTimeout(ctx, 2*time.Second)
	defer cancel()
	_ = s.store.LogInference(logCtx, InferenceLog{
		DeploymentID: deploymentID,
		InputData:    input,
		OutputData:   output,
		StatusCode:   statusCode,
		Latency:      latency,
	})
}

func writeJSON(w http.ResponseWriter, statusCode int, payload any) {
	body, _ := json.Marshal(payload)
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(statusCode)
	_, _ = w.Write(body)
}
