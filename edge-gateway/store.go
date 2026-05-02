package main

import (
	"context"
	"crypto/rand"
	"encoding/json"
	"errors"
	"fmt"
	"time"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"
)

var ErrDeploymentNotFound = errors.New("deployment not found")

type DeploymentTarget struct {
	ID          string
	InputSchema []byte
	Namespace   string
	ServiceName string
	ServicePort int
	ProxyURL    string
}

type InferenceLog struct {
	DeploymentID string
	InputData    any
	OutputData   any
	StatusCode   int
	Latency      time.Duration
}

type Store interface {
	LookupDeployment(ctx context.Context, userID string, slug string) (DeploymentTarget, error)
	LogInference(ctx context.Context, entry InferenceLog) error
	Ping(ctx context.Context) error
	Close()
}

type PostgresStore struct {
	pool *pgxpool.Pool
}

func NewPostgresStore(ctx context.Context, databaseURL string) (*PostgresStore, error) {
	if databaseURL == "" {
		return nil, errors.New("DATABASE_URL is required")
	}
	pool, err := pgxpool.New(ctx, databaseURL)
	if err != nil {
		return nil, err
	}
	return &PostgresStore{pool: pool}, nil
}

func (s *PostgresStore) LookupDeployment(ctx context.Context, userID string, slug string) (DeploymentTarget, error) {
	var target DeploymentTarget
	var inputSchema string
	err := s.pool.QueryRow(
		ctx,
		`
		SELECT
			d.id::text,
			COALESCE(d.input_schema, 'null'::jsonb)::text,
			d.k8s_namespace,
			d.k8s_service_name,
			d.k8s_service_port
		FROM deployment d
		JOIN deployment_status ds ON ds.id = d.status_id
		WHERE d.user_id = $1::uuid
		  AND d.slug = $2
		  AND ds.name = 'ACTIVE'
		  AND d.k8s_namespace IS NOT NULL
		  AND d.k8s_service_name IS NOT NULL
		  AND d.k8s_service_port IS NOT NULL
		`,
		userID,
		slug,
	).Scan(
		&target.ID,
		&inputSchema,
		&target.Namespace,
		&target.ServiceName,
		&target.ServicePort,
	)
	if errors.Is(err, pgx.ErrNoRows) {
		return DeploymentTarget{}, ErrDeploymentNotFound
	}
	if err != nil {
		return DeploymentTarget{}, err
	}
	if inputSchema != "null" {
		target.InputSchema = []byte(inputSchema)
	}
	return target, nil
}

func (s *PostgresStore) LogInference(ctx context.Context, entry InferenceLog) error {
	inputJSON, err := nullableJSON(entry.InputData)
	if err != nil {
		return err
	}
	outputJSON, err := nullableJSON(entry.OutputData)
	if err != nil {
		return err
	}
	_, err = s.pool.Exec(
		ctx,
		`
		INSERT INTO inference_log (
			id, deployment_id, input_data, output_data, status_code, latency_ms
		)
		VALUES ($1::uuid, $2::uuid, $3::jsonb, $4::jsonb, $5, $6)
		`,
		newUUID(),
		entry.DeploymentID,
		inputJSON,
		outputJSON,
		entry.StatusCode,
		float64(entry.Latency.Microseconds())/1000.0,
	)
	return err
}

func (s *PostgresStore) Ping(ctx context.Context) error {
	return s.pool.Ping(ctx)
}

func (s *PostgresStore) Close() {
	s.pool.Close()
}

func nullableJSON(value any) ([]byte, error) {
	if value == nil {
		return nil, nil
	}
	return json.Marshal(value)
}

func newUUID() string {
	var b [16]byte
	if _, err := rand.Read(b[:]); err != nil {
		panic(fmt.Errorf("generate uuid: %w", err))
	}
	b[6] = (b[6] & 0x0f) | 0x40
	b[8] = (b[8] & 0x3f) | 0x80
	return fmt.Sprintf("%x-%x-%x-%x-%x", b[0:4], b[4:6], b[6:8], b[8:10], b[10:16])
}
