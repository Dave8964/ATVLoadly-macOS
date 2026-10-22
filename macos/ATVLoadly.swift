import Cocoa
import ServiceManagement
import Sparkle

final class Controller: NSObject, NSApplicationDelegate, NSWindowDelegate, SPUUpdaterDelegate {
    private var status: NSStatusItem!
    private var controlsWindow: NSWindow?
    private let controlState = NSTextField(labelWithString: "Starting…")
    private let controlVersion = NSTextField(labelWithString: "Latest version: not checked")
    private let state = NSMenuItem(title: "Starting…", action: nil, keyEquivalent: "")
    private let latest = NSMenuItem(title: "Latest Available Version: not checked", action: nil, keyEquivalent: "")
    private var updater: SPUStandardUpdaterController?
    private var loginItem: NSMenuItem?
    private var releaseNotesURL: URL?
    private let home = FileManager.default.homeDirectoryForCurrentUser
    private var root: URL { home.appendingPathComponent("Library/Application Support/ATVLoadly") }
    private let base = URL(string: "http://127.0.0.1:5533")!
    private var timer: Timer?
    private var updateTarget: SUAppcastItem?
    private var preparedUpdate = false
    private var preparingUpdate = false

    func applicationDidFinishLaunching(_ note: Notification) {
        let updates = root.appendingPathComponent("updates")
        try? FileManager.default.createDirectory(at: updates, withIntermediateDirectories: true, attributes: [.posixPermissions: 0o700])
        try? String(ProcessInfo.processInfo.processIdentifier).write(to: updates.appendingPathComponent("ui-pid"), atomically: true, encoding: .utf8)
        status = NSStatusBar.system.statusItem(withLength: NSStatusItem.variableLength)
        status.button?.image = NSImage(systemSymbolName: "appletv", accessibilityDescription: "ATVLoadly")
        let menu = NSMenu()
        menu.addItem(state)
        add(menu, "Show Controls…", #selector(showControls))
        add(menu, "Open Dashboard", #selector(dashboard))
        add(menu, "View Logs", #selector(logs))
        menu.addItem(.separator())
        menu.addItem(NSMenuItem(title: "Current Version: \(Bundle.main.infoDictionary?["CFBundleShortVersionString"] as? String ?? "unknown")", action: nil, keyEquivalent: ""))
        menu.addItem(latest)
        add(menu, "Check for Updates…", #selector(check))
        add(menu, "Install Update…", #selector(check))
        add(menu, "Automatically Check for Updates", #selector(toggleChecks)).state = UserDefaults.standard.object(forKey: "SUEnableAutomaticChecks") as? Bool == false ? .off : .on
        add(menu, "Automatically Install Compatible Updates on Quit", #selector(autoInstall)).state = UserDefaults.standard.bool(forKey: "SUAutomaticallyUpdate") ? .on : .off
        add(menu, "View Release Notes", #selector(notes))
        menu.addItem(.separator())
        loginItem = add(menu, "Start at Login", #selector(login)); loginItem?.state = SMAppService.mainApp.status == .enabled ? .on : .off
        add(menu, "Quit", #selector(quit))
        status.menu = menu
        if let feed = Bundle.main.object(forInfoDictionaryKey: "SUFeedURL") as? String, feed.hasPrefix("https://"), Bundle.main.object(forInfoDictionaryKey: "SUPublicEDKey") != nil {
            updater = SPUStandardUpdaterController(startingUpdater: true, updaterDelegate: self, userDriverDelegate: nil)
        }
        do { try prepareService() } catch { show("Service setup failed", error.localizedDescription) }
        if FileManager.default.fileExists(atPath: updates.appendingPathComponent("pending.json").path) {
            let recovery = Process(); recovery.executableURL = updates.appendingPathComponent("watchdog"); recovery.arguments = ["watch",updates.appendingPathComponent("pending.json").path]
            try? recovery.run()
        }
        if !UserDefaults.standard.bool(forKey: "ATVInitialLoginRegistered") {
            do { try SMAppService.mainApp.register(); UserDefaults.standard.set(true,forKey:"ATVInitialLoginRegistered") } catch { show("Login startup needs attention",error.localizedDescription) }
        }
        if let resultData = try? Data(contentsOf: updates.appendingPathComponent("last-result.json")),
           let result = try? JSONSerialization.jsonObject(with: resultData) as? [String:Any],
           let phase = result["Phase"] as? String, phase.hasPrefix("rolled-back"),
           let backup = result["Backup"] as? String, UserDefaults.standard.string(forKey: "ATVReportedRollback") != backup {
            UserDefaults.standard.set(backup,forKey: "ATVReportedRollback")
            show("Update rolled back", phase + "\nYour previous application and data have been restored. Backups and diagnostics are in " + updates.path)
        }
        loginItem?.state = SMAppService.mainApp.status == .enabled ? .on : .off
        if SMAppService.mainApp.status == .requiresApproval { loginItem?.title = "Start at Login — approval required" }
        if !UserDefaults.standard.bool(forKey: "ATVControlsWindowPresented") {
            showControls()
            UserDefaults.standard.set(true, forKey: "ATVControlsWindowPresented")
        }
        poll()
        timer = Timer.scheduledTimer(withTimeInterval: 5, repeats: true) { [weak self] _ in self?.poll() }
    }
    func applicationShouldHandleReopen(_ sender: NSApplication, hasVisibleWindows flag: Bool) -> Bool {
        showControls()
        return true
    }
    @objc private func showControls() {
        if controlsWindow == nil {
            let window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 450, height: 270), styleMask: [.titled, .closable, .miniaturizable], backing: .buffered, defer: false)
            window.title = "ATVLoadly"
            window.delegate = self
            window.isReleasedWhenClosed = false
            let title = NSTextField(labelWithString: "ATVLoadly " + (Bundle.main.object(forInfoDictionaryKey: "CFBundleShortVersionString") as? String ?? ""))
            title.font = .boldSystemFont(ofSize: 20)
            let hint = NSTextField(wrappingLabelWithString: "ATVLoadly runs in the menu bar. You can also use this window to open your dashboard or install app updates.")
            let dashboardButton = NSButton(title: "Open Dashboard", target: self, action: #selector(dashboard))
            let updateButton = NSButton(title: "Check for Updates…", target: self, action: #selector(check))
            let logsButton = NSButton(title: "View Logs", target: self, action: #selector(logs))
            let buttons = NSStackView(views: [dashboardButton, updateButton, logsButton])
            buttons.orientation = .horizontal
            buttons.spacing = 10
            let stack = NSStackView(views: [title, hint, controlState, controlVersion, buttons])
            stack.orientation = .vertical
            stack.alignment = .leading
            stack.spacing = 16
            stack.translatesAutoresizingMaskIntoConstraints = false
            window.contentView!.addSubview(stack)
            NSLayoutConstraint.activate([stack.leadingAnchor.constraint(equalTo: window.contentView!.leadingAnchor, constant: 24), stack.trailingAnchor.constraint(equalTo: window.contentView!.trailingAnchor, constant: -24), stack.topAnchor.constraint(equalTo: window.contentView!.topAnchor, constant: 24)])
            window.center()
            controlsWindow = window
        }
        NSApp.setActivationPolicy(.regular)
        controlsWindow?.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)
    }
    func windowWillClose(_ notification: Notification) { NSApp.setActivationPolicy(.accessory) }
    @discardableResult private func add(_ menu: NSMenu, _ title: String, _ action: Selector) -> NSMenuItem {
        let item = NSMenuItem(title: title, action: action, keyEquivalent: "")
        item.target = self; menu.addItem(item); return item
    }
    private func run(_ args: [String]) throws {
        let p = Process(); p.executableURL = URL(fileURLWithPath: "/bin/launchctl"); p.arguments = args
        try p.run(); p.waitUntilExit()
        if p.terminationStatus != 0 { throw NSError(domain: "launchctl", code: Int(p.terminationStatus), userInfo: [NSLocalizedDescriptionKey: "launchctl failed (\(p.terminationStatus)); inspect service.log."]) }
    }
    private func prepareService() throws {
        let fm = FileManager.default
        try fm.createDirectory(at: root.appendingPathComponent("data"), withIntermediateDirectories: true)
        let config = root.appendingPathComponent("config.yaml")
        if !fm.fileExists(atPath: config.path) {
            let content = "server:\n  listen_addr: 127.0.0.1\n  work_dir: \(root.appendingPathComponent("data").path)\nlog:\n  log_file: \(root.appendingPathComponent("data/app.log").path)\n"
            try content.write(to: config, atomically: true, encoding: .utf8)
            try fm.setAttributes([.posixPermissions: 0o600], ofItemAtPath: config.path)
        }
        let agents = home.appendingPathComponent("Library/LaunchAgents")
        try fm.createDirectory(at: agents, withIntermediateDirectories: true)
        let label = "local.atvloadly.native.backend"
        let plist = agents.appendingPathComponent(label + ".plist")
        let bin = Bundle.main.bundleURL.appendingPathComponent("Contents/Resources/bin")
        let values: [String:Any] = ["Label":label,"AssociatedBundleIdentifiers":["local.atvloadly.native"],"ProgramArguments":[bin.appendingPathComponent("atvloadly").path,"server","-p","5533","-c",config.path],"RunAtLoad":true,"KeepAlive":true,"ThrottleInterval":5,"ProcessType":"Interactive","WorkingDirectory":root.path,"EnvironmentVariables":["PATH":bin.path + ":/usr/bin:/bin:/usr/sbin:/sbin","HOME":home.path,"ATVLOADLY_STARTUP_DIAGNOSTICS":"1","ATVLOADLY_UPDATE_JOURNAL":root.appendingPathComponent("updates/pending.json").path],"StandardOutPath":root.appendingPathComponent("service.log").path,"StandardErrorPath":root.appendingPathComponent("service-error.log").path]
        // Do not take the port or live database from an existing installation.
        let probe = Process(); probe.executableURL = URL(fileURLWithPath: "/bin/launchctl"); probe.arguments = ["print","gui/\(getuid())/local.atvloadly.agent"]; probe.standardOutput = FileHandle.nullDevice; probe.standardError = FileHandle.nullDevice
        try probe.run(); probe.waitUntilExit()
        if probe.terminationStatus == 0 { state.title = "Existing service active — replacement not enabled"; return }
        let running = Process(); running.executableURL = URL(fileURLWithPath: "/bin/launchctl"); running.arguments = ["print","gui/\(getuid())/\(label)"]; running.standardOutput = FileHandle.nullDevice; running.standardError = FileHandle.nullDevice
        try running.run(); running.waitUntilExit()
        if running.terminationStatus == 0 { return }
        let data = try PropertyListSerialization.data(fromPropertyList: values, format: .xml, options: 0)
        try data.write(to: plist, options: .atomic)
        try run(["bootstrap","gui/\(getuid())",plist.path])
    }
    private func poll() {
        var request = URLRequest(url: base.appendingPathComponent("native/ready")); request.timeoutInterval = 2
        URLSession.shared.dataTask(with: request) { data, response, _ in
            let json = data.flatMap { try? JSONSerialization.jsonObject(with: $0) as? [String:Any] }
            let probation = json?["probation"] as? Bool == true
            DispatchQueue.main.async { self.state.title = (response as? HTTPURLResponse)?.statusCode == 200 ? (probation ? "Validating update — refresh jobs paused" : "Backend ready") : "Replacement backend offline"; self.controlState.stringValue = self.state.title }
        }.resume()
    }
    private func show(_ title: String, _ text: String) { let a = NSAlert(); a.messageText = title; a.informativeText = text; a.runModal() }
    @objc private func dashboard() { NSWorkspace.shared.open(base) }
    @objc private func logs() { NSWorkspace.shared.open(root) }
    @objc private func check() {
        guard let updater else { show("Update publishing is not configured", "This build has no trusted macOS feed. GitHub authentication, a release repository and update-signing key are required before automatic updates can be enabled."); return }
        updater.checkForUpdates(nil)
    }
    @objc private func toggleChecks(_ sender: NSMenuItem) { sender.state = sender.state == .on ? .off : .on; UserDefaults.standard.set(sender.state == .on, forKey: "SUEnableAutomaticChecks"); updater?.updater.automaticallyChecksForUpdates = sender.state == .on }
    @objc private func autoInstall(_ sender: NSMenuItem) { sender.state = sender.state == .on ? .off : .on; UserDefaults.standard.set(sender.state == .on, forKey: "SUAutomaticallyUpdate"); updater?.updater.automaticallyDownloadsUpdates = sender.state == .on }
    @objc private func notes() { NSWorkspace.shared.open(releaseNotesURL ?? URL(string: "https://github.com/bitxeno/atvloadly/releases")!) }
    @objc private func login(_ sender: NSMenuItem) { if SMAppService.mainApp.status == .requiresApproval { SMAppService.openSystemSettingsLoginItems(); return }; do { if SMAppService.mainApp.status == .enabled {try SMAppService.mainApp.unregister()} else {try SMAppService.mainApp.register()}; sender.state = SMAppService.mainApp.status == .enabled ? .on : .off } catch {show("Login startup",error.localizedDescription)} }
    @objc private func quit() { NSApp.terminate(nil) }
    func updater(_ updater: SPUUpdater, didFindValidUpdate item: SUAppcastItem) { latest.title = "Latest Available Version: \(item.displayVersionString) (build \(item.versionString))"; controlVersion.stringValue = "Latest version: \(item.displayVersionString) (build \(item.versionString))"; releaseNotesURL = item.releaseNotesURL; status.button?.title = "↑" }
    func updater(_ updater: SPUUpdater, willInstallUpdate item: SUAppcastItem) { updateTarget = item }
    func updater(_ updater: SPUUpdater, willInstallUpdateOnQuit item: SUAppcastItem, immediateInstallationBlock: @escaping () -> Void) -> Bool {
        updateTarget = item
        return false
    }
    func applicationShouldTerminate(_ sender: NSApplication) -> NSApplication.TerminateReply {
        guard let target = updateTarget, !preparedUpdate else { return .terminateNow }
        if preparingUpdate { return .terminateLater }
        preparingUpdate = true
        let helper = Bundle.main.bundleURL.appendingPathComponent("Contents/Resources/bin/update-agent")
        let appPath = Bundle.main.bundleURL.path
        let dataRoot = root.path
        let build = target.versionString
        let upstream = target.displayVersionString
        DispatchQueue.global(qos: .userInitiated).async {
            let process = Process(); process.executableURL = helper
            process.arguments = ["prepare", appPath, dataRoot, build, upstream]
            let output = Pipe(); process.standardError = output
            var failure: String?
            do {
                try process.run()
                let data = output.fileHandleForReading.readDataToEndOfFile()
                process.waitUntilExit()
                if process.terminationStatus != 0 { failure = String(data: data, encoding: .utf8) ?? "Update preparation failed." }
            } catch { failure = error.localizedDescription }
            DispatchQueue.main.async {
                if let failure { self.preparingUpdate = false; self.updateTarget = nil; self.show("Update postponed", failure); sender.reply(toApplicationShouldTerminate: false) }
                else { self.preparedUpdate = true; sender.reply(toApplicationShouldTerminate: true) }
            }
        }
        return .terminateLater
    }

}
if CommandLine.arguments.contains("--unregister-login") {
    do { try SMAppService.mainApp.unregister(); UserDefaults.standard.set(false,forKey:"ATVInitialLoginRegistered"); exit(0) } catch { fputs("Login unregistration failed\n",stderr); exit(1) }
}
let app = NSApplication.shared
let controller = Controller()
app.delegate = controller
app.setActivationPolicy(.accessory)
app.run()
