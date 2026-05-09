# Production observability bundle

Docker-compose stack that collects OpenTelemetry traces & metrics from
the consciousness process and visualises them in Grafana.

## Components

| Service        | Port(s)              | Purpose                                   |
|----------------|----------------------|-------------------------------------------|
| otel-collector | 4317 (gRPC), 4318 (HTTP), 8889 | receives OTLP, fans out to Tempo / Prometheus |
| tempo          | 3200 (HTTP), 9095 (gRPC) | trace storage (retention 24h)          |
| prometheus     | 9090                 | metrics storage (retention 14d)           |
| grafana        | 3000                 | dashboards + datasources                  |

## Quick start

```bash
cd deploy/observability
docker-compose up -d
```

Wait ~15 seconds for services to come up, then:

- Grafana UI: <http://localhost:3000> (anonymous admin)
- A "Consciousness — Overview" dashboard is provisioned automatically.
- Prometheus UI: <http://localhost:9090>
- Tempo API: <http://localhost:3200>

## Wiring the consciousness app

Enable observability flags and point at the collector in
`config/flags.yaml`:

```yaml
observability_enabled: true
otel_enabled: true
```

And in `config/default.yaml`:

```yaml
observability:
  enabled: true
  otel_enabled: true
  otel_endpoint: "http://localhost:4317"
  otel_service_name: "agi-consciousness"
```

Restart the consciousness process. You should see tick spans appear in
Tempo within ~30 seconds and hysteresis metrics in Prometheus.

## Shutting down

```bash
docker-compose down             # stop containers
docker-compose down -v          # also delete volumes (traces + metrics)
```

## Production hardening (outside this README's scope)

- Put Grafana behind proper auth; disable anonymous access.
- Use TLS between the app and the collector (set `insecure: false`).
- Swap local storage for S3/GCS for traces (Tempo) and remote_write
  (Prometheus / Mimir).
- Separate retention policies by signal importance.
- Set up alerting via Grafana Alerting or Prometheus Alertmanager on
  key metrics: `consciousness_consciousness_hysteresis_value{channel="stress"} > 0.9`
  sustained for 5m, etc.
