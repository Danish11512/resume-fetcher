package main

import (
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"os"
)

type httpFetcher struct{ client *http.Client }

func (f httpFetcher) FetchJobs(url string) ([]Job, error) {
	req, err := http.NewRequest(http.MethodGet, url, nil)
	if err != nil {
		return nil, err
	}
	req.Header.Set("User-Agent", "resume-updater/1.0")
	resp, err := f.client.Do(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("job board returned %s", resp.Status)
	}
	return decodeJobs(resp.Body)
}

type listFetcher struct{ stdin io.Reader }

func (f listFetcher) FetchJobs(src string) ([]Job, error) {
	if src == "-" {
		return decodeJobs(f.stdin)
	}
	fh, err := os.Open(src)
	if err != nil {
		return nil, err
	}
	defer fh.Close()
	return decodeJobs(fh)
}

func decodeJobs(r io.Reader) ([]Job, error) {
	var payload struct {
		Jobs *[]Job `json:"jobs"`
	}
	if err := json.NewDecoder(r).Decode(&payload); err != nil {
		return nil, fmt.Errorf("decode job list: %w", err)
	}
	if payload.Jobs == nil {
		return nil, errors.New(`job list missing "jobs" field`)
	}
	return *payload.Jobs, nil
}
