package sensor

import "testing"

func TestString(t *testing.T) {
	if got := (Reading{"t1", 21.5}).String(); got != "t1=21.50" {
		t.Fatalf("got %q", got)
	}
}
