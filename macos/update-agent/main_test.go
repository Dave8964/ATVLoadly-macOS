package main

import (
	"encoding/json"
	"errors"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"sync/atomic"
	"testing"
	"time"
)

func TestRestorePreservesBackupAndFailedData(t *testing.T) {
	root := t.TempDir()
	old := filepath.Join(root, "backup")
	target := filepath.Join(root, "data")
	for _, p := range []string{old, target} {
		if err := os.Mkdir(p, 0700); err != nil {
			t.Fatal(err)
		}
	}
	if err := os.WriteFile(filepath.Join(old, "record"), []byte("paired-and-scheduled"), 0600); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(target, "record"), []byte("incompatible-migration"), 0600); err != nil {
		t.Fatal(err)
	}
	if err := restorePath(old, target); err != nil {
		t.Fatal(err)
	}
	for _, p := range []string{old, target} {
		b, err := os.ReadFile(filepath.Join(p, "record"))
		if err != nil || string(b) != "paired-and-scheduled" {
			t.Fatal("original data not restored")
		}
	}
	matches, _ := filepath.Glob(target + ".failed-*")
	if len(matches) != 1 {
		t.Fatal("failed data not preserved")
	}
}
func TestFailedRestoreDoesNotRemoveCurrentData(t *testing.T) {
	root := t.TempDir()
	target := filepath.Join(root, "data")
	if err := os.WriteFile(target, []byte("current"), 0600); err != nil {
		t.Fatal(err)
	}
	if err := restorePath(filepath.Join(root, "missing"), target); err == nil {
		t.Fatal("missing backup accepted")
	}
	b, _ := os.ReadFile(target)
	if string(b) != "current" {
		t.Fatal("current data changed")
	}
}

func TestWatcherCommitsOnlyHealthyReplacement(t *testing.T) {
	oldBase, oldVerify := backendBase, verifyApp
	defer func() { backendBase = oldBase; verifyApp = oldVerify }()
	verifyApp = func(string) error { return nil }
	root := t.TempDir()
	if err := os.MkdirAll(filepath.Join(root, "data"), 0700); err != nil {
		t.Fatal(err)
	}
	if err := os.MkdirAll(filepath.Join(root, "updates"), 0700); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(root, "data", ".native-control-token"), []byte("test-control-token"), 0600); err != nil {
		t.Fatal(err)
	}
	app := filepath.Join(root, "ATVLoadly.app")
	writeTestBundle(t, app, "2")
	j := journal{App: app, Root: root, Build: "2", Upstream: "0.7.3", Phase: "prepared", Counts: map[string]int64{"installed_apps": 2}}
	if err := save(pending(root), j); err != nil {
		t.Fatal(err)
	}
	var committed atomic.Bool
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path == "/native/ready" {
			_, _ = w.Write([]byte(`{"status":"ready","version":"v0.7.3","probation":true,"counts":{"installed_apps":2}}`))
			return
		}
		if r.URL.Path == "/native/commit" && r.Header.Get("X-ATV-Control") == "test-control-token" {
			committed.Store(true)
			w.WriteHeader(200)
			return
		}
		w.WriteHeader(401)
	}))
	defer server.Close()
	backendBase = server.URL
	if err := watch(pending(root)); err != nil {
		t.Fatal(err)
	}
	if !committed.Load() {
		t.Fatal("healthy backend was not committed")
	}
	if _, err := os.Stat(pending(root)); !os.IsNotExist(err) {
		t.Fatal("pending transaction not cleared")
	}
	var result journal
	b, err := os.ReadFile(filepath.Join(root, "updates", "last-result.json"))
	if err != nil {
		t.Fatal(err)
	}
	if err = json.Unmarshal(b, &result); err != nil || result.Phase != "healthy" {
		t.Fatal("success reported before health verification")
	}
}
func writeTestBundle(t *testing.T, app, version string) {
	t.Helper()
	if err := os.MkdirAll(filepath.Join(app, "Contents"), 0700); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(app, "Contents", "Info.plist"), []byte(`<?xml version="1.0"?><plist version="1.0"><dict><key>CFBundleVersion</key><string>`+version+`</string></dict></plist>`), 0600); err != nil {
		t.Fatal(err)
	}
}
func TestWatcherRollsBackFailedReplacement(t *testing.T) {
	oldStop, oldStart, oldClose, oldOpen := stopService, startService, closeMenuUI, reopenApp
	oldDeadline, oldPoll, oldBase := healthDeadline, pollDelay, backendBase
	defer func() {
		stopService = oldStop
		startService = oldStart
		closeMenuUI = oldClose
		reopenApp = oldOpen
		healthDeadline = oldDeadline
		pollDelay = oldPoll
		backendBase = oldBase
	}()
	stops, starts := 0, 0
	stopService = func() error { stops++; return nil }
	startService = func() error { starts++; return nil }
	closeMenuUI = func(journal) {}
	reopenApp = func(string) error { return nil }
	healthDeadline = 80 * time.Millisecond
	pollDelay = 10 * time.Millisecond
	root := t.TempDir()
	home := filepath.Join(root, "home")
	t.Setenv("HOME", home)
	backup := filepath.Join(root, "updates", "backup")
	app := filepath.Join(root, "ATVLoadly.app")
	writeTestBundle(t, filepath.Join(backup, "ATVLoadly.app"), "1")
	writeTestBundle(t, app, "2")
	for _, dir := range []string{filepath.Join(backup, "data"), filepath.Join(root, "data")} {
		if err := os.MkdirAll(dir, 0700); err != nil {
			t.Fatal(err)
		}
	}
	for _, file := range []struct{ path, value string }{{filepath.Join(backup, "data", "records"), "original-pairing-and-schedules"}, {filepath.Join(root, "data", "records"), "broken-migration"}} {
		if err := os.WriteFile(file.path, []byte(file.value), 0600); err != nil {
			t.Fatal(err)
		}
	}
	j := journal{App: app, Root: root, Build: "2", Upstream: "0.7.3", Backup: backup, Phase: "prepared", Present: []string{"ATVLoadly.app", "data"}}
	if err := save(pending(root), j); err != nil {
		t.Fatal(err)
	}
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) { w.WriteHeader(503) }))
	defer server.Close()
	backendBase = server.URL
	if err := watch(pending(root)); err != nil {
		t.Fatal(err)
	}
	if stops != 1 || starts != 1 {
		t.Fatal("service not stopped and restarted exactly once")
	}
	b, _ := os.ReadFile(filepath.Join(root, "data", "records"))
	if string(b) != "original-pairing-and-schedules" {
		t.Fatal("data was not restored")
	}
	b, _ = os.ReadFile(filepath.Join(app, "Contents", "Info.plist"))
	if !strings.Contains(string(b), "<string>1</string>") {
		t.Fatal("old bundle was not restored")
	}
}

func TestDatabaseGuardAllowsAdditionsButRejectsLostRecords(t *testing.T) {
	db := filepath.Join(t.TempDir(), "app.db")
	if err := command("/usr/bin/sqlite3", db, "CREATE TABLE installed_apps(id INTEGER PRIMARY KEY, source_url TEXT, signing_secret TEXT); INSERT INTO installed_apps VALUES(1,'https://example.com/nuvio','synthetic-test-secret');"); err != nil {
		t.Fatal(err)
	}
	before, err := databaseTable(db, "installed_apps", nil)
	if err != nil {
		t.Fatal(err)
	}
	if err := command("/usr/bin/sqlite3", db, "ALTER TABLE installed_apps ADD COLUMN new_setting TEXT DEFAULT '';"); err != nil {
		t.Fatal(err)
	}
	after, err := databaseTable(db, "installed_apps", before.Columns)
	if err != nil || after.Digest != before.Digest {
		t.Fatal("compatible added column rejected")
	}
	if err := command("/usr/bin/sqlite3", db, "UPDATE installed_apps SET signing_secret='lost';"); err != nil {
		t.Fatal(err)
	}
	after, err = databaseTable(db, "installed_apps", before.Columns)
	if err != nil {
		t.Fatal(err)
	}
	if after.Digest == before.Digest {
		t.Fatal("modified signing record was accepted")
	}
}
func TestConfigurationGuardPreservesSchedules(t *testing.T) {
	before := map[string]any{"task": map[string]any{"enabled": true, "schedule": "0 4 * * *"}}
	after := map[string]any{"task": map[string]any{"enabled": true, "schedule": "0 4 * * *", "new_setting": true}}
	if !containsSettings(after, before) {
		t.Fatal("new compatible setting rejected")
	}
	after["task"].(map[string]any)["schedule"] = "reset"
	if containsSettings(after, before) {
		t.Fatal("changed refresh schedule accepted")
	}
}

func TestCommittedSignatureFailureDoesNotRollBack(t *testing.T) {
	oldBase, oldVerify, oldStop := backendBase, verifyApp, stopService
	defer func() { backendBase, verifyApp, stopService = oldBase, oldVerify, oldStop }()
	verifyApp = func(string) error { return errors.New("signature invalid") }
	stopped := false
	stopService = func() error { stopped = true; return nil }
	root := t.TempDir()
	if err := os.MkdirAll(filepath.Join(root, "updates"), 0700); err != nil {
		t.Fatal(err)
	}
	app := filepath.Join(root, "ATVLoadly.app")
	writeTestBundle(t, app, "2")
	j := journal{App: app, Root: root, Build: "2", Upstream: "0.7.3", Phase: "commit-pending", Counts: map[string]int64{"installed_apps": 2}}
	if err := save(pending(root), j); err != nil {
		t.Fatal(err)
	}
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		_, _ = w.Write([]byte(`{"status":"ready","version":"v0.7.3","probation":false,"counts":{"installed_apps":2}}`))
	}))
	defer server.Close()
	backendBase = server.URL
	if err := watch(pending(root)); err == nil || !strings.Contains(err.Error(), "needs attention") {
		t.Fatalf("expected attention error, got %v", err)
	}
	if stopped {
		t.Fatal("attempted rollback after jobs could have resumed")
	}
	if _, err := os.Stat(pending(root)); err != nil {
		t.Fatal("lost pending recovery journal")
	}
}
