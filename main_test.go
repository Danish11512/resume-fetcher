package main

import (
	"encoding/json"
	"os"
	"path/filepath"
	"testing"
)

func TestParseInput(t *testing.T) {
	file := filepath.Join(t.TempDir(), "jobs.json")
	if err := os.WriteFile(file, []byte(`{"jobs":[]}`), 0o644); err != nil {
		t.Fatal(err)
	}
	cases := []struct {
		args    []string
		mode    srcMode
		wantErr bool
	}{
		{[]string{"https://api.ashbyhq.com/posting-api/job-board/ashby"}, modeURL, false},
		{[]string{"-"}, modeStdin, false},
		{[]string{file}, modeFile, false},
		{[]string{"/no/such/file.json"}, 0, true},
		{[]string{}, 0, true},
		{[]string{file, "extra"}, 0, true},
	}
	for _, c := range cases {
		_, mode, err := parseInput(c.args)
		if c.wantErr {
			if err == nil {
				t.Errorf("args %v: expected error", c.args)
			}
			continue
		}
		if err != nil {
			t.Errorf("args %v: unexpected error %v", c.args, err)
		}
		if mode != c.mode {
			t.Errorf("args %v: mode = %v, want %v", c.args, mode, c.mode)
		}
	}
}

func TestExtractAllMultiJob(t *testing.T) {
	jobs := []Job{
		{ID: "a", Title: "A", DescriptionPlain: "Requirements:\n- Python"},
		{ID: "b", Title: "B", DescriptionPlain: "Nice to have:\n- Rust"},
	}
	res := extractAll(newExtractor(), jobs)
	if len(res) != 2 {
		t.Fatalf("expected 2 results, got %d", len(res))
	}
	if res[0].JobID != "a" || res[1].JobID != "b" {
		t.Fatalf("job attribution wrong: %#v", res)
	}
	gotA := byCanonical(res[0].Required)
	if _, ok := gotA["Python"]; !ok {
		t.Errorf("job a missing required Python: %#v", res[0])
	}
	if _, ok := gotA["Rust"]; ok {
		t.Errorf("job a should not contain Rust")
	}
	if len(res[1].Required) != 0 || len(res[1].Preferred) != 1 || res[1].Preferred[0].Canonical != "Rust" {
		t.Errorf("job b wrong split: %#v", res[1])
	}
}

func TestWriteOutputs(t *testing.T) {
	dir := t.TempDir()
	res := []JobResult{{
		JobID: "j1", Title: "Eng",
		Required:  []Requirement{{Term: "Go", Canonical: "Go", Kind: "required", Section: "requirements"}},
		Preferred: []Requirement{},
	}}
	if err := writeOutputs(res, dir); err != nil {
		t.Fatalf("writeOutputs: %v", err)
	}
	data, err := os.ReadFile(filepath.Join(dir, "requirements.json"))
	if err != nil {
		t.Fatal(err)
	}
	var got []JobResult
	if err := json.Unmarshal(data, &got); err != nil {
		t.Fatalf("requirements.json not valid JSON: %v", err)
	}
	if len(got) != 1 || got[0].Required[0].Canonical != "Go" {
		t.Fatalf("unexpected requirements.json: %#v", got)
	}
	if _, err := os.Stat(filepath.Join(dir, "requirements.md")); err != nil {
		t.Fatal("requirements.md missing")
	}
}
