package main

import (
	"errors"
	"fmt"
	"io"
	"net/http"
	"os"
	"strings"
	"time"
)

type Job struct {
	ID               string `json:"id"`
	Title            string `json:"title"`
	DescriptionPlain string `json:"descriptionPlain"`
}

type Requirement struct {
	Term      string `json:"term"`
	Canonical string `json:"canonical"`
	Kind      string `json:"kind"`
	Section   string `json:"section,omitempty"`
}

type JobResult struct {
	JobID     string        `json:"jobId"`
	Title     string        `json:"title"`
	Required  []Requirement `json:"required"`
	Preferred []Requirement `json:"preferred"`
}

type Fetcher interface {
	FetchJobs(src string) ([]Job, error)
}

type Extractor interface {
	Extract(Job) []Requirement
}

type srcMode int

const (
	modeURL srcMode = iota
	modeFile
	modeStdin
)

func parseInput(args []string) (string, srcMode, error) {
	if len(args) != 1 {
		return "", 0, errors.New("usage: resume-updater <jobs.json | - | board-url>")
	}
	src := args[0]
	switch {
	case src == "-":
		return src, modeStdin, nil
	case strings.HasPrefix(src, "http://") || strings.HasPrefix(src, "https://"):
		return src, modeURL, nil
	default:
		if _, err := os.Stat(src); err != nil {
			return "", 0, fmt.Errorf("cannot read jobs file %q: %w", src, err)
		}
		return src, modeFile, nil
	}
}

func newFetcher(mode srcMode, stdin io.Reader) Fetcher {
	if mode == modeURL {
		return httpFetcher{client: &http.Client{Timeout: 30 * time.Second}}
	}
	return listFetcher{stdin: stdin}
}

func extractAll(ex Extractor, jobs []Job) []JobResult {
	results := make([]JobResult, 0, len(jobs))
	for _, j := range jobs {
		r := JobResult{JobID: j.ID, Title: j.Title, Required: []Requirement{}, Preferred: []Requirement{}}
		for _, req := range ex.Extract(j) {
			if req.Kind == "preferred" {
				r.Preferred = append(r.Preferred, req)
			} else {
				r.Required = append(r.Required, req)
			}
		}
		results = append(results, r)
	}
	return results
}

func main() {
	src, mode, err := parseInput(os.Args[1:])
	if err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(2)
	}
	jobs, err := newFetcher(mode, os.Stdin).FetchJobs(src)
	if err != nil {
		fmt.Fprintf(os.Stderr, "fetch jobs: %v\n", err)
		os.Exit(1)
	}
	results := extractAll(newExtractor(), jobs)
	if err := writeOutputs(results, "."); err != nil {
		fmt.Fprintf(os.Stderr, "write outputs: %v\n", err)
		os.Exit(1)
	}
	for _, r := range results {
		fmt.Printf("%s (%s): required=%d preferred=%d\n", r.Title, r.JobID, len(r.Required), len(r.Preferred))
	}
	fmt.Printf("%d jobs -> requirements.json, requirements.md\n", len(results))
}
