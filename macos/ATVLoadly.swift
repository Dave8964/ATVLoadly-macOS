import Cocoa
import ServiceManagement
import Sparkle

final class Controller: NSObject, NSApplicationDelegate, SPUUpdaterDelegate {
    private var status: NSStatusItem!
    private let state = NSMenuItem(title: "Starting…", action: nil, keyEquivalent: "")
    private let latest = NSMenuItem(title: "Latest Available Version: not checked", action: nil, keyEquivalent: "")
    private var updater: SPUStandardUpdaterController?
    private let home = FileManager.default.homeDirectoryForCurrentUser
    private var root: URL { home.appendingPathComponent("Library/Application Support/ATVLoadly") }
    private let base = URL(string: "http://127.0.0.1:5533")!
    private var timer: Timer?

    func applicationDidFinishLaunching(_ note: Notification) {
        status = NSStatusBar.system.statusItem(withLength: NSStatusItem.variableLength)
        status.button?.image = NSImage(systemSymbolName: "appletv", accessibilityDescription: "ATVLoadly")
        let menu = NSMenu()
        menu.addItem(state)
        add(menu, "Open Dashboard", #selector(dashboard))
        add(menu, "View Logs", #selector(logs))
        menu.addItem(.separator())
        menu.addItem(NSMenuItem(title: "Current Version: \(Bundle.main.infoDictionary?["CFBundleShortVersionString"] as? String ?? "unknown")", action: nil, keyEquivalent: ""))
        menu.addItem(latest)
        add(menu, "Check for Updates…", #selector(check))
        add(menu, "Install Update…", #selector(check))
        add(menu, "Automatically Check for Updates", #selector(toggleChecks)).state = UserDefaults.standard.object(forKey: "SUEnableAutomaticChecks") as? Bool == false ? .off : .on
        // Silent installation stays disabled until the rollback qualification suite passes.
        let auto = add(menu, "Automatically Install Compatible Updates (qualification pending)", #selector(autoInstall))
        auto.isEnabled = false
        add(menu, "View Release Notes", #selector(notes))
        menu.addItem(.separator())
        add(menu, "Start at Login", #selector(login)).state = SMAppService.mainApp.status == .enabled ? .on : .off
        add(menu, "Quit", #selector(quit))
        status.menu = menu
        if let feed = Bundle.main.object(forInfoDictionaryKey: "SUFeedURL") as? String, feed.hasPrefix("https://"), Bundle.main.object(forInfoDictionaryKey: "SUPublicEDKey") != nil {
            updater = SPUStandardUpdaterController(startingUpdater: true, updaterDelegate: self, userDriverDelegate: nil)
        }
        do { try prepareService() } catch { show("Service setup failed", error.localizedDescription) }
        poll()
        timer = Timer.scheduledTimer(withTimeInterval: 5, repeats: true) { [weak self] _ in self?.poll() }
    }
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
        let values: [String:Any] = ["Label":label,"ProgramArguments":[bin.appendingPathComponent("atvloadly").path,"server","-p","5533","-c",config.path],"RunAtLoad":true,"KeepAlive":true,"ThrottleInterval":5,"ProcessType":"Background","WorkingDirectory":root.path,"EnvironmentVariables":["PATH":bin.path + ":/usr/bin:/bin:/usr/sbin:/sbin","HOME":home.path],"StandardOutPath":root.appendingPathComponent("service.log").path,"StandardErrorPath":root.appendingPathComponent("service-error.log").path]
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
        URLSession.shared.dataTask(with: request) { _, response, _ in
            DispatchQueue.main.async { self.state.title = (response as? HTTPURLResponse)?.statusCode == 200 ? "Backend ready" : "Replacement backend offline" }
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
    @objc private func autoInstall() {}
    @objc private func notes() { NSWorkspace.shared.open(URL(string: "https://github.com/bitxeno/atvloadly/releases")!) }
    @objc private func login(_ sender: NSMenuItem) { do { if SMAppService.mainApp.status == .enabled {try SMAppService.mainApp.unregister()} else {try SMAppService.mainApp.register()}; sender.state = SMAppService.mainApp.status == .enabled ? .on : .off } catch {show("Login startup",error.localizedDescription)} }
    @objc private func quit() { NSApp.terminate(nil) }
    func updater(_ updater: SPUUpdater, didFindValidUpdate item: SUAppcastItem) { latest.title = "Latest Available Version: \(item.displayVersionString)"; status.button?.title = "↑" }
    func updater(_ updater: SPUUpdater, mayPerform updateCheck: SPUUpdateCheck) throws {
        // Fail closed until transactional rollback has been verified against a published build.
        throw NSError(domain: "ATVLoadly.UpdateQualification", code: 1, userInfo: [NSLocalizedDescriptionKey:"Update installation is disabled pending end-to-end rollback qualification. Your installed app and data are unchanged."])
    }
}
let app = NSApplication.shared
let controller = Controller()
app.delegate = controller
app.setActivationPolicy(.accessory)
app.run()
