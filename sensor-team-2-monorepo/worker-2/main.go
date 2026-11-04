package main

import (
	"fmt"

	"sensor-team-2/internal/sensor"
)

func main() {
	fmt.Println("worker processed", sensor.Reading{ID: "t2", Value: 3})
}
