package main

import (
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

const jobsJSON = `{"jobs":[{"id":"j1","title":"Eng","descriptionPlain":"Requirements:\n- Go"},{"id":"j2","title":"PM","descriptionPlain":"Nice to have:\n- Figma"}]}`

func TestFetchJobsURL(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		w.Write([]byte(jobsJSON))
	}))
	defer srv.Close()
	jobs, err := httpFetcher{client: srv.Client()}.FetchJobs(srv.URL)
	if err != nil {
		t.Fatalf("FetchJobs: %v", err)
	}
	if len(jobs) != 2 || jobs[0].ID != "j1" || jobs[1].Title != "PM" {
		t.Fatalf("unexpected jobs: %#v", jobs)
	}
}

func TestFetchJobs404(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusNotFound)
	}))
	defer srv.Close()
	if _, err := (httpFetcher{client: srv.Client()}).FetchJobs(srv.URL); err == nil {
		t.Fatal("expected error on 404")
	}
}

func TestFetchJobsMalformed(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Write([]byte("not json"))
	}))
	defer srv.Close()
	if _, err := (httpFetcher{client: srv.Client()}).FetchJobs(srv.URL); err == nil {
		t.Fatal("expected error on malformed JSON")
	}
}

func TestFetchJobsMissingField(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Write([]byte(`{"other":true}`))
	}))
	defer srv.Close()
	if _, err := (httpFetcher{client: srv.Client()}).FetchJobs(srv.URL); err == nil {
		t.Fatal("expected error on missing jobs field")
	}
}

func TestListFetcherFile(t *testing.T) {
	path := filepath.Join(t.TempDir(), "jobs.json")
	if err := os.WriteFile(path, []byte(jobsJSON), 0o644); err != nil {
		t.Fatal(err)
	}
	jobs, err := listFetcher{}.FetchJobs(path)
	if err != nil {
		t.Fatalf("FetchJobs: %v", err)
	}
	if len(jobs) != 2 {
		t.Fatalf("expected 2 jobs, got %#v", jobs)
	}
}

func TestListFetcherStdin(t *testing.T) {
	f := listFetcher{stdin: strings.NewReader(jobsJSON)}
	jobs, err := f.FetchJobs("-")
	if err != nil {
		t.Fatalf("FetchJobs: %v", err)
	}
	if len(jobs) != 2 {
		t.Fatalf("expected 2 jobs, got %#v", jobs)
	}
}
