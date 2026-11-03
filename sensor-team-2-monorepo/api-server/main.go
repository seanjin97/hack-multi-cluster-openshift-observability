package main

import (
	"encoding/json"
	"fmt"
	"net/http"
	"sensor-team-2/internal/sensor"
)

func main() {
	http.HandleFunc("/reading", func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")

		reading := sensor.Reading{ID: "t1", Value: 21.522}
		w.WriteHeader(http.StatusOK)
		if err := json.NewEncoder(w).Encode(reading); err != nil {
			// Handle encoding error (e.g., system logs) if necessary
			http.Error(w, err.Error(), http.StatusInternalServerError)
			return
		}
	})
	fmt.Println("listening on :8080")
	_ = http.ListenAndServe(":8080", nil)
}
