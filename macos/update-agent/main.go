package main

import (
	"bytes"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"io/fs"
	"net/http"
	"os"
	"os/exec"
	"path/filepath"
	"reflect"
	"regexp"
	"strconv"
	"strings"
	"syscall"
	"time"
)

type tableSnapshot struct {
	Columns []string
	Digest  string
}
type journal struct {
	App, Root, Build, Upstream, Backup, Phase string
	Present                                   []string
	Counts                                    map[string]int64
	Tables                                    map[string]tableSnapshot
	Protected                                 map[string]string
	Settings                                  map[string]any
	Created                                   time.Time
}

var client = &http.Client{Timeout: 3 * time.Second}
var backendBase = "http://127.0.0.1:5533"
var healthDeadline = 90 * time.Second
var pollDelay = time.Second
var stopService = stop
var startService = start
var closeMenuUI = closeUI
var reopenApp = func(app string) error { return command("/usr/bin/open", app) }
var verifyApp = func(app string) error { return command("/usr/bin/codesign", "--verify", "--deep", "--strict", app) }
var numeric = regexp.MustCompile(`^[0-9]+(\.[0-9]+)*$`)

const label = "local.atvloadly.native.backend"

func command(name string, args ...string) error {
	out, err := exec.Command(name, args...).CombinedOutput()
	if err != nil {
		return fmt.Errorf("%s failed: %w: %.400s", filepath.Base(name), err, out)
	}
	return nil
}
func copyPath(src, dst string) error {
	return command("/usr/bin/ditto", "--norsrc", "--noextattr", src, dst)
}
func save(path string, v any) error {
	b, err := json.MarshalIndent(v, "", "  ")
	if err != nil {
		return err
	}
	if err = os.WriteFile(path+".tmp", b, 0600); err != nil {
		return err
	}
	return os.Rename(path+".tmp", path)
}
func pending(root string) string { return filepath.Join(root, "updates", "pending.json") }
func agentPlist() string {
	home, _ := os.UserHomeDir()
	return filepath.Join(home, "Library", "LaunchAgents", label+".plist")
}
func domain() string { return fmt.Sprintf("gui/%d", os.Getuid()) }
func stop() error {
	output, err := exec.Command("/bin/launchctl", "print", domain()+"/"+label).Output()
	if err != nil {
		return err
	}
	match := regexp.MustCompile(`(?m)^\s*pid = ([0-9]+)$`).FindStringSubmatch(string(output))
	if err := command("/bin/launchctl", "bootout", domain()+"/"+label); err != nil {
		return err
	}
	if len(match) > 1 {
		pid, _ := strconv.Atoi(match[1])
		deadline := time.Now().Add(10 * time.Second)
		for syscall.Kill(pid, 0) == nil {
			if time.Now().After(deadline) {
				return errors.New("backend did not stop; refusing to snapshot live data")
			}
			time.Sleep(50 * time.Millisecond)
		}
	}
	return nil
}
func start() error { return command("/bin/launchctl", "bootstrap", domain(), agentPlist()) }
func control(root, action string) error {
	token, err := os.ReadFile(filepath.Join(root, "data", ".native-control-token"))
	if err != nil {
		return err
	}
	req, err := http.NewRequest("POST", backendBase+"/native/"+action, bytes.NewReader(nil))
	if err != nil {
		return err
	}
	req.Header.Set("X-ATV-Control", strings.TrimSpace(string(token)))
	response, err := client.Do(req)
	if err != nil {
		return err
	}
	defer func() { _ = response.Body.Close() }()
	if response.StatusCode == 409 {
		return errors.New("an installation, pairing, or login session is active; wait for it to finish or close an idle installation page, then retry")
	}
	if response.StatusCode != 200 {
		return fmt.Errorf("backend %s refused (HTTP %d)", action, response.StatusCode)
	}
	return nil
}
func databaseTable(db, table string, columns []string) (tableSnapshot, error) {
	if table != "installed_apps" && table != "signing_identities" && table != "saved_sources" {
		return tableSnapshot{}, errors.New("unsupported protected database table")
	}
	if len(columns) == 0 {
		out, err := exec.Command("/usr/bin/sqlite3", "-readonly", "-json", db, "PRAGMA table_info("+table+");").Output()
		if err != nil {
			return tableSnapshot{}, err
		}
		var info []struct{ Name string }
		if err = json.Unmarshal(out, &info); err != nil {
			return tableSnapshot{}, err
		}
		for _, column := range info {
			columns = append(columns, column.Name)
		}
	}
	var quoted []string
	for _, column := range columns {
		if !regexp.MustCompile(`^[a-zA-Z_][a-zA-Z0-9_]*$`).MatchString(column) {
			return tableSnapshot{}, errors.New("unsupported database column name")
		}
		quoted = append(quoted, `"`+column+`"`)
	}
	if len(quoted) == 0 {
		return tableSnapshot{}, errors.New("missing protected database table")
	}
	out, err := exec.Command("/usr/bin/sqlite3", "-readonly", "-json", db, "SELECT "+strings.Join(quoted, ",")+" FROM "+table+" ORDER BY id;").Output()
	if err != nil {
		return tableSnapshot{}, err
	}
	var rows any
	if len(bytes.TrimSpace(out)) == 0 {
		out = []byte("[]")
	}
	if err = json.Unmarshal(out, &rows); err != nil {
		return tableSnapshot{}, err
	}
	canonical, err := json.Marshal(rows)
	if err != nil {
		return tableSnapshot{}, err
	}
	digest := sha256.Sum256(canonical)
	return tableSnapshot{Columns: columns, Digest: hex.EncodeToString(digest[:])}, nil
}
func protectedFiles(j *journal) error {
	j.Protected = map[string]string{}
	if b, err := os.ReadFile(filepath.Join(j.Backup, "config.yaml")); err == nil {
		digest := sha256.Sum256(b)
		j.Protected[filepath.Join("config", "config.yaml")] = hex.EncodeToString(digest[:])
	} else if !os.IsNotExist(err) {
		return err
	}
	for _, name := range []string{"data", "plume", "lockdown"} {
		base := filepath.Join(j.Backup, name)
		if _, err := os.Stat(base); os.IsNotExist(err) {
			continue
		}
		err := filepath.WalkDir(base, func(path string, entry fs.DirEntry, err error) error {
			if err != nil {
				return err
			}
			rel, err := filepath.Rel(base, path)
			if err != nil {
				return err
			}
			if entry.IsDir() {
				for _, component := range strings.Split(rel, string(filepath.Separator)) {
					if component == "log" || component == "upload" || component == "tmp" || component == "signing-work" {
						return filepath.SkipDir
					}
				}
				return nil
			}
			if entry.Type()&os.ModeSymlink != 0 {
				return errors.New("symbolic signing-data files need a reviewed migration")
			}
			if !entry.Type().IsRegular() || strings.HasSuffix(path, ".log") || strings.HasSuffix(path, "-wal") || strings.HasSuffix(path, "-shm") || entry.Name() == "app.db" {
				return nil
			}
			b, err := os.ReadFile(path)
			if err != nil {
				return err
			}
			if name == "data" && rel == "settings.json" {
				return json.Unmarshal(b, &j.Settings)
			}
			digest := sha256.Sum256(b)
			j.Protected[filepath.Join(name, rel)] = hex.EncodeToString(digest[:])
			return nil
		})
		if err != nil {
			return err
		}
	}
	return nil
}
func containsSettings(current, previous any) bool {
	old, ok := previous.(map[string]any)
	if !ok {
		return reflect.DeepEqual(current, previous)
	}
	now, ok := current.(map[string]any)
	if !ok {
		return false
	}
	for key, value := range old {
		other, exists := now[key]
		if !exists || !containsSettings(other, value) {
			return false
		}
	}
	return true
}
func verifyPreservation(j journal) error {
	for table, before := range j.Tables {
		after, err := databaseTable(filepath.Join(j.Root, "data", "app.db"), table, before.Columns)
		if err != nil || after.Digest != before.Digest {
			return fmt.Errorf("replacement changed protected records in %s", table)
		}
	}
	home, _ := os.UserHomeDir()
	roots := map[string]string{"config": j.Root, "data": filepath.Join(j.Root, "data"), "plume": filepath.Join(home, ".config", "PlumeImpactor"), "lockdown": filepath.Join(home, ".config", "atvloadly", "lockdown")}
	for rel, expected := range j.Protected {
		pieces := strings.SplitN(rel, string(filepath.Separator), 2)
		if len(pieces) != 2 {
			return errors.New("invalid protected-file record")
		}
		b, err := os.ReadFile(filepath.Join(roots[pieces[0]], pieces[1]))
		if err != nil {
			return errors.New("replacement removed a protected signing or application file")
		}
		digest := sha256.Sum256(b)
		if hex.EncodeToString(digest[:]) != expected {
			return errors.New("replacement changed a protected signing or application file")
		}
	}
	if j.Settings != nil {
		b, err := os.ReadFile(filepath.Join(j.Root, "data", "settings.json"))
		if err != nil {
			return err
		}
		var current any
		if err = json.Unmarshal(b, &current); err != nil {
			return err
		}
		if !containsSettings(current, j.Settings) {
			return errors.New("replacement changed existing configuration or schedules")
		}
	}
	return nil
}

func snapshot(j *journal) error {
	if err := copyPath(j.App, filepath.Join(j.Backup, "ATVLoadly.app")); err != nil {
		return err
	}
	j.Present = append(j.Present, "ATVLoadly.app")
	home, _ := os.UserHomeDir()
	for _, pair := range [][2]string{
		{filepath.Join(j.Root, "data"), "data"}, {filepath.Join(j.Root, "config.yaml"), "config.yaml"},
		{filepath.Join(home, ".config", "PlumeImpactor"), "plume"}, {filepath.Join(home, ".config", "atvloadly", "lockdown"), "lockdown"},
	} {
		if _, err := os.Stat(pair[0]); os.IsNotExist(err) {
			continue
		} else if err != nil {
			return err
		}
		if err := copyPath(pair[0], filepath.Join(j.Backup, pair[1])); err != nil {
			return err
		}
		j.Present = append(j.Present, pair[1])
	}
	db := filepath.Join(j.Backup, "data", "app.db")
	out, err := exec.Command("/usr/bin/sqlite3", "-readonly", db, "PRAGMA integrity_check;").Output()
	if err != nil || strings.TrimSpace(string(out)) != "ok" {
		return errors.New("backup database integrity validation failed")
	}
	j.Counts = map[string]int64{}
	j.Tables = map[string]tableSnapshot{}
	for _, table := range []string{"installed_apps", "signing_identities", "saved_sources"} {
		out, err := exec.Command("/usr/bin/sqlite3", "-readonly", db, "SELECT COUNT(*) FROM "+table+";").Output()
		if err != nil {
			return err
		}
		count, err := strconv.ParseInt(strings.TrimSpace(string(out)), 10, 64)
		if err != nil {
			return err
		}
		j.Counts[table] = count
		state, err := databaseTable(db, table, nil)
		if err != nil {
			return err
		}
		j.Tables[table] = state
	}
	if err := protectedFiles(j); err != nil {
		return err
	}
	return verifyApp(filepath.Join(j.Backup, "ATVLoadly.app"))
}
func prepare(app, root, build, upstream string) error {
	if !filepath.IsAbs(app) || !filepath.IsAbs(root) || !strings.HasSuffix(app, ".app") || !numeric.MatchString(build) || !numeric.MatchString(strings.TrimPrefix(upstream, "v")) {
		return errors.New("invalid update arguments")
	}
	if _, err := os.Stat(pending(root)); err == nil {
		return errors.New("another update is pending")
	}
	if err := verifyApp(app); err != nil {
		return err
	}
	if err := control(root, "quiesce"); err != nil {
		return err
	}
	if err := stopService(); err != nil {
		_ = control(root, "resume")
		return err
	}
	resume := true
	defer func() {
		if resume {
			_ = startService()
		}
	}()
	backup := filepath.Join(root, "updates", fmt.Sprintf("backup-%d", time.Now().UnixNano()))
	if err := os.MkdirAll(backup, 0700); err != nil {
		return err
	}
	j := journal{App: app, Root: root, Build: build, Upstream: strings.TrimPrefix(upstream, "v"), Backup: backup, Phase: "prepared", Created: time.Now()}
	if err := snapshot(&j); err != nil {
		return err
	}
	exe, err := os.Executable()
	if err != nil {
		return err
	}
	watcher := filepath.Join(root, "updates", "watchdog")
	if err = copyPath(exe, watcher); err != nil {
		return err
	}
	if err = save(pending(root), j); err != nil {
		return err
	}
	log, err := os.OpenFile(filepath.Join(root, "updates", "watchdog.log"), os.O_WRONLY|os.O_CREATE|os.O_APPEND, 0600)
	if err != nil {
		_ = os.Remove(pending(root))
		return err
	}
	defer func() { _ = log.Close() }()
	cmd := exec.Command(watcher, "watch", pending(root))
	cmd.Stdout = log
	cmd.Stderr = log
	cmd.SysProcAttr = &syscall.SysProcAttr{Setsid: true}
	if err = cmd.Start(); err != nil {
		_ = os.Remove(pending(root))
		return err
	}
	resume = false
	_ = cmd.Process.Release()
	return nil
}
func ready(j journal) bool {
	output, err := exec.Command("/usr/libexec/PlistBuddy", "-c", "Print :CFBundleVersion", filepath.Join(j.App, "Contents", "Info.plist")).Output()
	if err != nil || strings.TrimSpace(string(output)) != j.Build {
		return false
	}
	r, err := client.Get(backendBase + "/native/ready")
	if err != nil {
		return false
	}
	defer func() { _ = r.Body.Close() }()
	var state struct {
		Status, Version string
		Probation       bool
		Counts          map[string]int64
	}
	if r.StatusCode != 200 || json.NewDecoder(io.LimitReader(r.Body, 4096)).Decode(&state) != nil {
		return false
	}
	return state.Status == "ready" && strings.TrimPrefix(state.Version, "v") == j.Upstream && state.Probation && reflect.DeepEqual(state.Counts, j.Counts)
}
func readyAfterCommit(j journal) bool {
	output, err := exec.Command("/usr/libexec/PlistBuddy", "-c", "Print :CFBundleVersion", filepath.Join(j.App, "Contents", "Info.plist")).Output()
	if err != nil || strings.TrimSpace(string(output)) != j.Build {
		return false
	}
	r, err := client.Get(backendBase + "/native/ready")
	if err != nil {
		return false
	}
	defer func() { _ = r.Body.Close() }()
	var state struct {
		Status, Version string
		Probation       bool
		Counts          map[string]int64
	}
	if r.StatusCode != 200 || json.NewDecoder(io.LimitReader(r.Body, 4096)).Decode(&state) != nil {
		return false
	}
	return state.Status == "ready" && strings.TrimPrefix(state.Version, "v") == j.Upstream
}
func restorePath(backup, target string) error {
	if _, err := os.Stat(backup); err != nil {
		return err
	}
	staged := target + ".restore-" + strconv.FormatInt(time.Now().UnixNano(), 10)
	if err := copyPath(backup, staged); err != nil {
		return err
	}
	if _, err := os.Stat(target); err == nil {
		if err = os.Rename(target, target+".failed-"+strconv.FormatInt(time.Now().UnixNano(), 10)); err != nil {
			return err
		}
	}
	return os.Rename(staged, target)
}
func closeUI(j journal) {
	b, err := os.ReadFile(filepath.Join(j.Root, "updates", "ui-pid"))
	if err != nil {
		return
	}
	pid, err := strconv.Atoi(strings.TrimSpace(string(b)))
	if err != nil || pid < 2 {
		return
	}
	out, err := exec.Command("/bin/ps", "-p", strconv.Itoa(pid), "-o", "comm=").Output()
	if err == nil && strings.TrimSpace(string(out)) == filepath.Join(j.App, "Contents", "MacOS", "ATVLoadly") {
		_ = syscall.Kill(pid, syscall.SIGTERM)
	}
}
func rollback(j journal, cause error) error {
	_ = stopService()
	closeMenuUI(j)
	if err := restorePath(filepath.Join(j.Backup, "ATVLoadly.app"), j.App); err != nil {
		return err
	}
	home, _ := os.UserHomeDir()
	for _, pair := range [][2]string{{"data", filepath.Join(j.Root, "data")}, {"config.yaml", filepath.Join(j.Root, "config.yaml")}, {"plume", filepath.Join(home, ".config", "PlumeImpactor")}, {"lockdown", filepath.Join(home, ".config", "atvloadly", "lockdown")}} {
		present := false
		for _, name := range j.Present {
			if name == pair[0] {
				present = true
			}
		}
		if !present {
			continue
		}
		if err := restorePath(filepath.Join(j.Backup, pair[0]), pair[1]); err != nil {
			return err
		}
	}
	j.Phase = "rolled-back: " + cause.Error()
	if err := save(filepath.Join(j.Root, "updates", "last-result.json"), j); err != nil {
		return err
	}
	if err := os.Remove(pending(j.Root)); err != nil {
		return err
	}
	if err := startService(); err != nil {
		return err
	}
	return reopenApp(j.App)
}
func watch(path string) error {
	lock, err := os.OpenFile(path+".lock", os.O_CREATE|os.O_RDWR, 0600)
	if err != nil {
		return err
	}
	defer func() { _ = lock.Close() }()
	if err = syscall.Flock(int(lock.Fd()), syscall.LOCK_EX|syscall.LOCK_NB); err != nil {
		return nil
	}
	defer func() { _ = syscall.Flock(int(lock.Fd()), syscall.LOCK_UN) }()

	b, err := os.ReadFile(path)
	if err != nil {
		return err
	}
	var j journal
	if err = json.Unmarshal(b, &j); err != nil {
		return err
	}
	deadline := time.Now().Add(healthDeadline)
	for time.Now().Before(deadline) {
		if ready(j) || ((j.Phase == "commit-pending" || j.Phase == "healthy") && readyAfterCommit(j)) {
			if err := verifyApp(j.App); err != nil {
				if j.Phase != "prepared" {
					return fmt.Errorf("committed update signature needs attention: %w", err)
				}
				return rollback(j, err)
			}
			if j.Phase == "prepared" {
				if err := verifyPreservation(j); err != nil {
					return rollback(j, err)
				}
			}
			j.Phase = "commit-pending"
			if err = save(path, j); err != nil {
				return err
			}
			// Once jobs may resume, do not roll back underneath a signing operation.
			for range 10 {
				if err = control(j.Root, "commit"); err == nil {
					j.Phase = "healthy"
					if err = save(filepath.Join(j.Root, "updates", "last-result.json"), j); err != nil {
						return err
					}
					return os.Remove(path)
				}
				time.Sleep(pollDelay)
			}
			return fmt.Errorf("replacement passed health validation but commit acknowledgement failed: %w", err)
		}
		time.Sleep(pollDelay)
	}
	if j.Phase == "commit-pending" || j.Phase == "healthy" {
		return errors.New("committed update needs attention; automatic rollback is prohibited after jobs may have resumed")
	}
	return rollback(j, errors.New("replacement failed version, readiness or probation checks within 90 seconds"))
}
func main() {
	var err error
	switch {
	case len(os.Args) == 6 && os.Args[1] == "prepare":
		err = prepare(os.Args[2], os.Args[3], os.Args[4], os.Args[5])
	case len(os.Args) == 3 && os.Args[1] == "watch":
		err = watch(os.Args[2])
	default:
		err = errors.New("usage: update-agent prepare APP ROOT BUILD UPSTREAM | watch JOURNAL")
	}
	if err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
}
