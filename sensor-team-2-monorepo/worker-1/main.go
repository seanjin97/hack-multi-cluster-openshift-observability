package main

import (
	"fmt"
	"math/rand/v2"
	"net/http"
	"strconv"
	"time"

	"sensor-team-2/internal/sensor"

	"github.com/prometheus/client_golang/prometheus"
	"github.com/prometheus/client_golang/prometheus/promauto"
	"github.com/prometheus/client_golang/prometheus/promhttp"
)

var (
	readings = promauto.NewCounterVec(prometheus.CounterOpts{
		Name: "sensor_readings_total",
		Help: "Sensor readings taken, by outcome.",
	}, []string{"outcome"})
	lastValue = promauto.NewGauge(prometheus.GaugeOpts{
		Name: "sensor_reading_celsius",
		Help: "Last successful sensor reading.",
	})
	// Golden-path RED metric (doc/app-teams/1-metrics.md): _count = traffic + errors, _bucket = latency.
	duration = promauto.NewHistogramVec(prometheus.HistogramOpts{
		Name: "http_request_duration_seconds",
		Help: "HTTP request duration.",
	}, []string{"path", "method", "status"})
)

// read simulates a sensor: ~10% of reads fail, the rest return 15-30°C.
func read() (sensor.Reading, bool) {
	if rand.Float64() < 0.1 {
		return sensor.Reading{}, false
	}
	return sensor.Reading{ID: "t1", Value: 15 + rand.Float64()*15}, true
}

type statusWriter struct {
	http.ResponseWriter
	code int
}

func (w *statusWriter) WriteHeader(c int) { w.code = c; w.ResponseWriter.WriteHeader(c) }

// instrument records duration by path (a fixed route, never the raw URL), method and status.
func instrument(path string, h http.HandlerFunc) {
	http.HandleFunc(path, func(w http.ResponseWriter, r *http.Request) {
		start, sw := time.Now(), &statusWriter{w, 200}
		h(sw, r)
		duration.WithLabelValues(path, r.Method, strconv.Itoa(sw.code)).Observe(time.Since(start).Seconds())
	})
}

func main() {
	// pre-create: failures show 0, not "No data"
	readings.WithLabelValues("failure")

	go func() {
		for range time.Tick(5 * time.Second) {
			r, ok := read()
			if !ok {
				readings.WithLabelValues("failure").Inc()
				continue
			}
			readings.WithLabelValues("success").Inc()
			lastValue.Set(r.Value)
		}
	}()

	// /read: take a reading on demand. 503 when the sensor fails, 10-210ms to answer.
	instrument("/read", func(w http.ResponseWriter, _ *http.Request) {
		time.Sleep(time.Duration(10+rand.IntN(200)) * time.Millisecond)
		r, ok := read()
		if !ok {
			readings.WithLabelValues("failure").Inc()
			http.Error(w, "sensor failed", http.StatusServiceUnavailable)
			return
		}
		readings.WithLabelValues("success").Inc()
		lastValue.Set(r.Value)
		fmt.Fprintf(w, "%.1f\n", r.Value)
	})

	http.Handle("/metrics", promhttp.Handler())
	fmt.Println("metrics on :8080/metrics")
	_ = http.ListenAndServe(":8080", nil)
}
