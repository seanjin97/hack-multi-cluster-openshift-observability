package main

import (
	"fmt"
	"math/rand/v2"
	"net/http"
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
)

// read simulates a sensor: ~10% of reads fail, the rest return 15-30°C.
func read() (sensor.Reading, bool) {
	if rand.Float64() < 0.1 {
		return sensor.Reading{}, false
	}
	return sensor.Reading{ID: "t1", Value: 15 + rand.Float64()*15}, true
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

	http.Handle("/metrics", promhttp.Handler())
	fmt.Println("metrics on :8080/metrics")
	_ = http.ListenAndServe(":8080", nil)
}
