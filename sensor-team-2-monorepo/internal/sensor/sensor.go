package sensor

import "fmt"

type Reading struct {
	ID    string
	Value float64
}

func (r Reading) String() string { return fmt.Sprintf("%s=%.2f", r.ID, r.Value) }
