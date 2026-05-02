package main

import (
	"context"
	"encoding/json"
	"errors"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"github.com/golang-jwt/jwt/v5"
)

type fakeStore struct {
	target DeploymentTarget
	err    error
	logs   []InferenceLog
}

func (s *fakeStore) LookupDeployment(_ context.Context, userID string, slug string) (DeploymentTarget, error) {
	if userID != "00000000-0000-0000-0000-000000000001" || slug != "fraud-prod" {
		return DeploymentTarget{}, ErrDeploymentNotFound
	}
	return s.target, s.err
}

func (s *fakeStore) LogInference(_ context.Context, entry InferenceLog) error {
	s.logs = append(s.logs, entry)
	return nil
}

func (s *fakeStore) Ping(_ context.Context) error {
	return nil
}

func (s *fakeStore) Close() {}

func TestDeploymentSlug(t *testing.T) {
	slug, ok := deploymentSlug("/api/v1/deployments/fraud-prod:predict")
	if !ok || slug != "fraud-prod" {
		t.Fatalf("expected fraud-prod slug, got %q ok=%v", slug, ok)
	}
	if _, ok := deploymentSlug("/api/v1/deployments/fraud-prod/other:predict"); ok {
		t.Fatal("nested path should not parse as deployment slug")
	}
}

func TestPredictRejectsMissingBearerToken(t *testing.T) {
	store := gatewayStore()
	server := NewServer(store, testConfig()).routes()

	req := httptest.NewRequest(http.MethodPost, "/api/v1/deployments/fraud-prod:predict", strings.NewReader(`{"x":1}`))
	rec := httptest.NewRecorder()
	server.ServeHTTP(rec, req)

	if rec.Code != http.StatusUnauthorized {
		t.Fatalf("expected 401, got %d", rec.Code)
	}
	if len(store.logs) != 0 {
		t.Fatalf("unauthenticated requests should not be logged without a deployment, got %d logs", len(store.logs))
	}
}

func TestPredictValidatesInputSchemaBeforeProxying(t *testing.T) {
	store := gatewayStore()
	server := NewServer(store, testConfig()).routes()

	req := authenticatedRequest(`{"score":"bad"}`)
	rec := httptest.NewRecorder()
	server.ServeHTTP(rec, req)

	if rec.Code != http.StatusUnprocessableEntity {
		t.Fatalf("expected 422, got %d body=%s", rec.Code, rec.Body.String())
	}
	if len(store.logs) != 1 {
		t.Fatalf("expected one inference log, got %d", len(store.logs))
	}
	if store.logs[0].StatusCode != http.StatusUnprocessableEntity {
		t.Fatalf("expected logged 422, got %d", store.logs[0].StatusCode)
	}
}

func TestPredictProxiesAndLogsResponse(t *testing.T) {
	upstream := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/predict" {
			t.Fatalf("expected /predict, got %s", r.URL.Path)
		}
		writeJSON(w, http.StatusOK, map[string]any{"predictions": []int{1}})
	}))
	defer upstream.Close()

	store := gatewayStore()
	store.target.ProxyURL = upstream.URL + "/predict"
	server := NewServer(store, testConfig())
	server.httpClient = upstream.Client()

	req := authenticatedRequest(`{"score":1.5}`)
	rec := httptest.NewRecorder()
	server.routes().ServeHTTP(rec, req)

	if rec.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d body=%s", rec.Code, rec.Body.String())
	}
	var payload map[string][]int
	if err := json.Unmarshal(rec.Body.Bytes(), &payload); err != nil {
		t.Fatalf("invalid response json: %v", err)
	}
	if payload["predictions"][0] != 1 {
		t.Fatalf("unexpected response: %#v", payload)
	}
	if len(store.logs) != 1 || store.logs[0].StatusCode != http.StatusOK {
		t.Fatalf("expected logged 200, got %#v", store.logs)
	}
}

func TestReadyReportsDatabaseFailure(t *testing.T) {
	store := gatewayStore()
	store.err = errors.New("not used")
	server := NewServer(&pingFailStore{fakeStore: store}, testConfig()).routes()

	req := httptest.NewRequest(http.MethodGet, "/ready", nil)
	rec := httptest.NewRecorder()
	server.ServeHTTP(rec, req)

	if rec.Code != http.StatusServiceUnavailable {
		t.Fatalf("expected 503, got %d", rec.Code)
	}
}

type pingFailStore struct {
	*fakeStore
}

func (s *pingFailStore) Ping(_ context.Context) error {
	return errors.New("database down")
}

func gatewayStore() *fakeStore {
	return &fakeStore{
		target: DeploymentTarget{
			ID:          "10000000-0000-0000-0000-000000000001",
			InputSchema: []byte(`{"type":"object","required":["score"],"properties":{"score":{"type":"number"}}}`),
			Namespace:   "mldlc",
			ServiceName: "model-fraud-prod",
			ServicePort: 20001,
		},
	}
}

func testConfig() Config {
	return Config{
		SecretKey:              "test-secret",
		RequestTimeout:         5 * time.Second,
		MaxBodyBytes:           1 << 20,
		CORSAllowedOriginRegex: `^https?://([a-z0-9-]+\.)?mldlc\.local(:\d+)?$`,
	}
}

func authenticatedRequest(body string) *http.Request {
	req := httptest.NewRequest(http.MethodPost, "/api/v1/deployments/fraud-prod:predict", strings.NewReader(body))
	req.Header.Set("Authorization", "Bearer "+testJWT())
	req.Header.Set("Content-Type", "application/json")
	return req
}

func testJWT() string {
	token := jwt.NewWithClaims(jwt.SigningMethodHS256, jwt.MapClaims{
		"sub": "00000000-0000-0000-0000-000000000001",
		"exp": time.Now().Add(time.Hour).Unix(),
	})
	value, err := token.SignedString([]byte("test-secret"))
	if err != nil {
		panic(err)
	}
	return value
}
