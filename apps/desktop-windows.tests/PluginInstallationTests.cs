using System.Text;
using System.Text.Json;
using System.IO;
using PasswordDetective.Desktop.Plugins.Installation;
using PasswordDetective.Desktop.Plugins.DynamicReview;
using PasswordDetective.Desktop.Plugins.Packages;
using PasswordDetective.Desktop.Plugins.Permissions;
using PasswordDetective.Desktop.Plugins.Registry;
using PasswordDetective.Desktop.Plugins.Runtime;
using PasswordDetective.Desktop.Plugins.Safety;
using PasswordDetective.Desktop.Plugins.Storage;
using PasswordDetective.Desktop.Plugins.Windows;

namespace PasswordDetective.Desktop.Tests;

public sealed class PluginInstallationTests : IDisposable
{
    private readonly string _directory = Path.Combine(
        Path.GetTempPath(),
        "password-detective-install-tests",
        Guid.NewGuid().ToString("N"));
    private readonly PluginPackageTestFactory _factory = new();

    public PluginInstallationTests() => Directory.CreateDirectory(_directory);

    [Fact]
    public async Task InstallUpgradeRollbackAndUninstallKeepOnlyCurrentAndPreviousVersions()
    {
        var paths = new PluginStoragePaths(Path.Combine(_directory, "plugins"));
        var registry = new PluginRegistry(paths);
        var validator = new RecordingValidator();
        var installer = CreateInstaller(paths, registry, validator);
        var version1 = _factory.Create(_directory, version: "1.0.0");
        var version2 = _factory.Create(_directory, version: "1.1.0");
        var version3 = _factory.Create(_directory, version: "1.2.0");

        var first = await installer.InstallLocalAsync(
            version1,
            ["ui:command", "storage:private"]);
        var second = await installer.InstallLocalAsync(
            version2,
            ["ui:command", "storage:private"]);
        var third = await installer.InstallLocalAsync(
            version3,
            ["ui:command", "storage:private"]);

        Assert.Equal(PluginSource.LocalUnreviewed, first.Plugin.Source);
        Assert.Equal("1.2.0", third.Plugin.CurrentVersion);
        Assert.Equal("1.1.0", third.Plugin.RollbackVersion);
        Assert.Equal(2, validator.MigrationCount);
        Assert.Equal(2, third.Plugin.Versions.Count);
        Assert.False(Directory.Exists(paths.InstalledVersionDirectory(first.Plugin.PluginId, "1.0.0")));
        Assert.True(Directory.Exists(paths.InstalledVersionDirectory(second.Plugin.PluginId, "1.1.0")));
        Assert.True(Directory.Exists(paths.InstalledVersionDirectory(third.Plugin.PluginId, "1.2.0")));
        Assert.True(third.Plugin.PermissionConsents!.TryGetValue("1.2.0", out var consent));
        Assert.Equal(["storage:private", "ui:command"], consent!.GrantedCapabilities);
        Assert.Equal(["storage:private", "ui:command"], consent.ApprovedCapabilities);
        Assert.Equal("completed", third.Plugin.MigrationRecords!["1.2.0"].Status);
        Assert.Equal("1.1.0", third.Plugin.MigrationRecords["1.2.0"].FromVersion);
        var migrationStep = Assert.Single(third.Plugin.MigrationRecords["1.2.0"].Steps!);
        Assert.Equal("settings.copy", migrationStep.StepId);
        Assert.Equal(2, migrationStep.AttemptCount);

        var privateStorage = new PluginPrivateStorage(paths);
        await privateStorage.SetAsync(
            third.Plugin.PluginId,
            "settings.current",
            JsonSerializer.SerializeToElement(new { retained = true }));

        var rolledBack = await installer.RollbackAsync(third.Plugin.PluginId);

        Assert.Equal("1.1.0", rolledBack.CurrentVersion);
        Assert.Equal("1.2.0", rolledBack.RollbackVersion);
        Assert.Equal(4, validator.ValidationCount);

        await installer.UninstallAsync(third.Plugin.PluginId);

        Assert.Null(await registry.GetAsync(third.Plugin.PluginId));
        Assert.False(Directory.Exists(Path.Combine(paths.InstalledDirectory, third.Plugin.PluginId)));
        Assert.True(Directory.Exists(paths.PluginDataDirectory(third.Plugin.PluginId)));
        Assert.NotNull(await privateStorage.GetAsync(third.Plugin.PluginId, "settings.current"));
    }

    [Fact]
    public async Task FailedHealthValidationRemovesNewVersionAndDoesNotWriteRegistry()
    {
        var paths = new PluginStoragePaths(Path.Combine(_directory, "failed-plugins"));
        var registry = new PluginRegistry(paths);
        var validator = new RecordingValidator { Failure = new InvalidOperationException("synthetic health failure") };
        var installer = CreateInstaller(paths, registry, validator);
        var package = _factory.Create(_directory, pluginId: "com.synthetic.failed-plugin");

        await Assert.ThrowsAsync<InvalidOperationException>(
            () => installer.InstallLocalAsync(package, ["ui:command", "storage:private"]));

        Assert.Null(await registry.GetAsync("com.synthetic.failed-plugin"));
        Assert.False(Directory.Exists(paths.InstalledVersionDirectory("com.synthetic.failed-plugin", "1.0.0")));
    }

    [Fact]
    public async Task FailedMigrationKeepsCurrentVersionAndRemovesNewDirectory()
    {
        var paths = new PluginStoragePaths(Path.Combine(_directory, "migration-failure"));
        var registry = new PluginRegistry(paths);
        var validator = new RecordingValidator();
        var installer = CreateInstaller(paths, registry, validator);
        var version1 = _factory.Create(_directory, version: "1.0.0");
        var version2 = _factory.Create(_directory, version: "1.1.0");
        await installer.InstallLocalAsync(version1, ["ui:command", "storage:private"]);
        var privateStorage = new PluginPrivateStorage(paths);
        await privateStorage.SetAsync(
            "com.synthetic.local-plugin",
            "migration.state",
            JsonSerializer.SerializeToElement(new { version = 1 }));
        validator.MigrationAction = () => privateStorage.SetAsync(
            "com.synthetic.local-plugin",
            "migration.state",
            JsonSerializer.SerializeToElement(new { version = 2 }));
        validator.MigrationFailure = new PluginMigrationException(
            "synthetic migration failure",
            [new PluginMigrationStepExecution("settings.copy", "failed", 3)]);

        await Assert.ThrowsAsync<PluginMigrationException>(
            () => installer.InstallLocalAsync(version2, ["ui:command", "storage:private"]));

        var installed = await registry.GetAsync("com.synthetic.local-plugin");
        Assert.NotNull(installed);
        Assert.Equal("1.0.0", installed!.CurrentVersion);
        Assert.False(Directory.Exists(paths.InstalledVersionDirectory(installed.PluginId, "1.1.0")));
        var restored = await privateStorage.GetAsync(installed.PluginId, "migration.state");
        Assert.Equal(1, restored?.GetProperty("version").GetInt32());
        Assert.Equal("failed", installed.MigrationRecords!["1.1.0"].Status);
        Assert.Equal("1.0.0", installed.MigrationRecords["1.1.0"].FromVersion);
        Assert.Equal(3, Assert.Single(installed.MigrationRecords["1.1.0"].Steps!).AttemptCount);
    }

    [Fact]
    public async Task SameVersionWithDifferentArtifactIsRejectedAsImmutable()
    {
        var paths = new PluginStoragePaths(Path.Combine(_directory, "immutable-plugins"));
        var registry = new PluginRegistry(paths);
        var installer = CreateInstaller(paths, registry, new RecordingValidator());
        var first = _factory.Create(_directory, pluginId: "com.synthetic.immutable-plugin");
        var replacement = _factory.Create(
            _directory,
            pluginId: "com.synthetic.immutable-plugin",
            additionalFiles: new Dictionary<string, byte[]>
            {
                ["assets/different.txt"] = Encoding.UTF8.GetBytes("different artifact"),
            });
        await installer.InstallLocalAsync(first, ["ui:command", "storage:private"]);

        var exception = await Assert.ThrowsAsync<PluginInstallException>(
            () => installer.InstallLocalAsync(replacement, ["ui:command", "storage:private"]));

        Assert.Contains("版本不可变", exception.Message);
    }

    [Fact]
    public async Task DowngradeInstallIsRejectedAndRollbackRemainsExplicit()
    {
        var paths = new PluginStoragePaths(Path.Combine(_directory, "downgrade-plugins"));
        var registry = new PluginRegistry(paths);
        var installer = CreateInstaller(paths, registry, new RecordingValidator());
        var current = _factory.Create(_directory, version: "1.2.0");
        var older = _factory.Create(_directory, version: "1.1.0");

        await installer.InstallLocalAsync(current, ["ui:command", "storage:private"]);

        var exception = await Assert.ThrowsAsync<PluginInstallException>(
            () => installer.InstallLocalAsync(older, ["ui:command", "storage:private"]));

        Assert.Contains("已拒绝降级安装", exception.Message);
        var installed = await registry.GetAsync("com.synthetic.local-plugin");
        Assert.NotNull(installed);
        Assert.Equal("1.2.0", installed!.CurrentVersion);
    }

    [Fact]
    public async Task ReinstallDetectsTamperedInstalledFile()
    {
        var paths = new PluginStoragePaths(Path.Combine(_directory, "tampered-plugins"));
        var registry = new PluginRegistry(paths);
        var installer = CreateInstaller(paths, registry, new RecordingValidator());
        var package = _factory.Create(_directory, pluginId: "com.synthetic.tampered-plugin");
        var installed = await installer.InstallLocalAsync(
            package,
            ["ui:command", "storage:private"]);
        var manifestPath = Path.Combine(
            paths.InstalledVersionDirectory(installed.Plugin.PluginId, installed.Plugin.CurrentVersion),
            PluginPackageVerifier.ManifestPath);
        await File.AppendAllTextAsync(manifestPath, "tampered");

        var exception = await Assert.ThrowsAsync<PluginInstallException>(
            () => installer.InstallLocalAsync(package, ["ui:command", "storage:private"]));

        Assert.Contains("摘要不一致", exception.Message);
    }

    [Fact]
    public async Task RegistryPersistsOnlyLocalUnreviewedSourceAndUsesAtomicReplacement()
    {
        var paths = new PluginStoragePaths(Path.Combine(_directory, "registry-plugins"));
        var registry = new PluginRegistry(paths);
        var installer = CreateInstaller(paths, registry, new RecordingValidator());
        var package = _factory.Create(_directory, pluginId: "com.synthetic.registry-plugin");
        await installer.InstallLocalAsync(package, ["ui:command", "storage:private"]);

        var reloaded = await new PluginRegistry(paths).GetAsync("com.synthetic.registry-plugin");

        Assert.NotNull(reloaded);
        Assert.Equal(PluginSource.LocalUnreviewed, reloaded!.Source);
        Assert.Equal(PluginSource.LocalUnreviewedLabel, reloaded.ReviewLabel);
        Assert.Empty(Directory.EnumerateFiles(paths.RootDirectory, "*.tmp"));
    }

    [Fact]
    public async Task CorruptRegistryIsRejectedWithoutAutomaticReset()
    {
        var paths = new PluginStoragePaths(Path.Combine(_directory, "corrupt-registry"));
        paths.EnsureDirectories();
        await File.WriteAllTextAsync(
            paths.RegistryPath,
            """{"schema_version":1,"plugins":[{"plugin_id":"synthetic.invalid","source":"market_reviewed","current_version":"1.0.0","versions":{}}]}""");
        var before = await File.ReadAllTextAsync(paths.RegistryPath);

        await Assert.ThrowsAsync<PluginRegistryException>(
            () => new PluginRegistry(paths).GetAllAsync());

        Assert.Equal(before, await File.ReadAllTextAsync(paths.RegistryPath));
    }

    [Fact]
    public async Task PrivateStorageUsesOpaqueFilesAndEnforcesQuota()
    {
        var paths = new PluginStoragePaths(Path.Combine(_directory, "private-storage"));
        var storage = new PluginPrivateStorage(paths, quotaBytes: 1024 * 1024);
        var value = JsonSerializer.SerializeToElement(new { message = "synthetic value" });

        await storage.SetAsync("com.synthetic.storage-plugin", "settings.current", value);
        var loaded = await storage.GetAsync("com.synthetic.storage-plugin", "settings.current");

        Assert.Equal("synthetic value", loaded?.GetProperty("message").GetString());
        var files = Directory.EnumerateFiles(
            Path.Combine(paths.PluginDataDirectory("com.synthetic.storage-plugin"), "storage"))
            .ToArray();
        Assert.Single(files);
        Assert.DoesNotContain("settings.current", Path.GetFileName(files[0]));
        Assert.Throws<ArgumentException>(
            () => storage.Remove("com.synthetic.storage-plugin", "../escape"));
    }

    [Fact]
    public async Task RealPackageInstallsAndExecutesInsideAppContainer()
    {
        var pluginOutput = FindSyntheticPluginOutput();
        var runtimeFiles = Directory.EnumerateFiles(pluginOutput)
            .Where(path => Path.GetExtension(path) is not ".pdb")
            .ToDictionary(
                path => Path.GetFileName(path) == "pdpp-synthetic-plugin.exe"
                    ? "bin/windows-x64/plugin.exe"
                    : $"bin/windows-x64/{Path.GetFileName(path)}",
                File.ReadAllBytes,
                StringComparer.Ordinal);
        var package = _factory.Create(
            _directory,
            pluginId: "com.synthetic.real-plugin",
            runtimeFiles: runtimeFiles);
        var paths = new PluginStoragePaths(Path.Combine(_directory, "real-plugins"));
        var registry = new PluginRegistry(paths);
        var logs = new PluginLogStore(paths);
        var execution = new PluginExecutionService(
            paths,
            logs,
            apiBroker: null,
            themeService: null,
            NoOpWindowsPluginIsolationPolicy.Instance);
        var installer = CreateInstaller(paths, registry, execution);
        var installed = await installer.InstallLocalAsync(
            package,
            ["ui:command", "storage:private"]);
        var runtime = new PluginRuntimeService(
            registry,
            execution,
            new PluginSafeMode(paths),
            logs);

        var result = await runtime.ExecuteAsync(
            installed.Plugin.PluginId,
            "echo",
            JsonSerializer.SerializeToElement(new { message = "synthetic appcontainer" }));

        Assert.Equal("csharp", result.GetProperty("language").GetString());
        Assert.Equal(
            "synthetic appcontainer",
            result.GetProperty("output").GetProperty("message").GetString());
        Assert.Empty(Directory.EnumerateDirectories(
            Path.Combine(paths.RunsDirectory, installed.Plugin.PluginId)));
    }

    [Fact]
    public async Task OfficialInspectorReadsSelectedPackageThroughBrokerInsideAppContainer()
    {
        var targetPackage = _factory.Create(
            _directory,
            pluginId: "com.synthetic.inspection-target",
            additionalFiles: new Dictionary<string, byte[]>
            {
                ["sbom.cdx.json"] = Encoding.UTF8.GetBytes(
                    """{"bomFormat":"CycloneDX","specVersion":"1.5","version":1,"components":[]}"""),
                ["source/Program.cs"] = Encoding.UTF8.GetBytes(
                    "internal static class SyntheticInspectionTarget { }")
            });
        var pluginOutput = FindOfficialInspectorOutput();
        var runtimeFiles = Directory.EnumerateFiles(pluginOutput)
            .Where(path => Path.GetExtension(path) is not ".pdb")
            .ToDictionary(
                path => Path.GetFileName(path) == "password-detective-official-plugin-inspector.exe"
                    ? "bin/windows-x64/plugin.exe"
                    : $"bin/windows-x64/{Path.GetFileName(path)}",
                File.ReadAllBytes,
                StringComparer.Ordinal);
        var inspectorPackage = _factory.Create(
            _directory,
            pluginId: "com.passworddetective.official-plugin-inspector",
            requiredCapabilities: ["ui:command", "file:read:selected"],
            optionalCapabilities: [],
            commandId: "inspect",
            commandTitle: "检查插件包",
            commandSchemaPath: "schemas/inspect.schema.json",
            commandSchema: Encoding.UTF8.GetBytes(
                """{"type":"object","required":["package"],"properties":{"package":{"type":"string","title":"PDPKG 插件包","format":"file"}}}"""),
            runtimeFiles: runtimeFiles);
        var paths = new PluginStoragePaths(Path.Combine(_directory, "official-inspector-plugins"));
        var registry = new PluginRegistry(paths);
        var logs = new PluginLogStore(paths);
        var execution = new PluginExecutionService(
            paths,
            logs,
            apiBroker: null,
            themeService: null,
            NoOpWindowsPluginIsolationPolicy.Instance);
        var installer = CreateInstaller(paths, registry, execution);
        var installed = await installer.InstallLocalAsync(
            inspectorPackage,
            ["ui:command", "file:read:selected"]);
        var runtime = new PluginRuntimeService(
            registry,
            execution,
            new PluginSafeMode(paths),
            logs);

        var result = await runtime.ExecuteAsync(
            installed.Plugin.PluginId,
            "inspect",
            JsonSerializer.SerializeToElement(new { package = targetPackage }));

        Assert.Equal("passed", result.GetProperty("status").GetString());
        Assert.Equal(
            "com.synthetic.inspection-target",
            result.GetProperty("plugin_id").GetString());
        Assert.True(result.GetProperty("summary").GetProperty("signature_valid").GetBoolean());
        Assert.False(result.GetRawText().Contains(targetPackage, StringComparison.OrdinalIgnoreCase));
    }

    [Fact]
    public async Task DynamicReviewExecutorForcesAllHiddenCanariesInFreshAppContainers()
    {
        var pluginOutput = FindSyntheticPluginOutput();
        var runtimeFiles = Directory.EnumerateFiles(pluginOutput)
            .Where(path => Path.GetExtension(path) is not ".pdb")
            .ToDictionary(
                path => Path.GetFileName(path) == "pdpp-synthetic-plugin.exe"
                    ? "bin/windows-x64/plugin.exe"
                    : $"bin/windows-x64/{Path.GetFileName(path)}",
                File.ReadAllBytes,
                StringComparer.Ordinal);
        var package = _factory.Create(
            _directory,
            pluginId: "com.synthetic.dynamic-review",
            runtimeFiles: runtimeFiles);
        var inspection = await new PluginPackageVerifier().VerifyAsync(package);
        Assert.Equal(["echo"], inspection.Manifest.Commands.Select(command => command.Id));
        var workspace = Path.Combine(_directory, "dynamic-review-workspace");
        var executor = new DynamicReviewExecutor(
            new PluginPackageVerifier(),
            NoOpWindowsPluginIsolationPolicy.Instance);

        var result = await executor.ExecuteAsync(
            package,
            "synthetic-task-001",
            workspace,
            freshEnvironment: true);

        Assert.Equal("blocked", result.Outcome);
        Assert.True(result.EvidenceComplete);
        Assert.True(result.FreshEnvironment);
        Assert.Equal(64, result.DestructionProofSha256.Length);
        Assert.True(result.Summary.TryGetValue("appcontainer", out var appContainer));
        Assert.True(Assert.IsType<bool>(appContainer));
        Assert.True(Assert.IsType<bool>(result.Summary["canary_probe_invoked"]));
        Assert.True(Assert.IsType<bool>(result.Summary["canary_environment_invoked"]));
        Assert.True(Assert.IsType<bool>(result.Summary["canary_spawn_child_invoked"]));
        Assert.True(Assert.IsType<bool>(result.Summary["canary_hang_invoked"]));
        Assert.True(Assert.IsType<bool>(result.Summary["canary_oversized_output_invoked"]));
        Assert.True(Assert.IsType<bool>(result.Summary["timeout_enforced"]));
        Assert.True(Assert.IsType<bool>(result.Summary["message_limit_enforced"]));
        Assert.Contains(result.Findings, finding => finding.RuleId == "PD-DYNAMIC-013" && finding.Blocked);
        Assert.False(Assert.IsType<bool>(result.Summary["canary_file_read"]));
        Assert.False(Assert.IsType<bool>(result.Summary["canary_network_connected"]));
        Assert.False(Assert.IsType<bool>(result.Summary["canary_secret_visible"]));
        Assert.False(Directory.Exists(Path.Combine(workspace, "synthetic-task-001")));
    }

    public void Dispose()
    {
        if (Directory.Exists(_directory))
        {
            Directory.Delete(_directory, recursive: true);
        }
    }

    private static PluginInstaller CreateInstaller(
        PluginStoragePaths paths,
        PluginRegistry registry,
        IPluginInstallValidator validator) => new(
        paths,
        new PluginPackageVerifier(),
        new PluginPermissionPolicy(),
        registry,
        validator);

    private static string FindSyntheticPluginOutput()
    {
        var root = new DirectoryInfo(AppContext.BaseDirectory);
        while (root is not null
               && !Directory.Exists(Path.Combine(root.FullName, "tests", "fixtures", "pdpp", "csharp")))
        {
            root = root.Parent;
        }

        if (root is null)
        {
            throw new DirectoryNotFoundException("Repository root was not found.");
        }

        return Path.Combine(
            root.FullName,
            "tests",
            "fixtures",
            "pdpp",
            "csharp",
            "bin",
            "Release",
            "net10.0");
    }

    private static string FindOfficialInspectorOutput()
    {
        var root = new DirectoryInfo(AppContext.BaseDirectory);
        while (root is not null
               && !Directory.Exists(Path.Combine(root.FullName, "plugins", "official-plugin-inspector")))
        {
            root = root.Parent;
        }

        if (root is null)
        {
            throw new DirectoryNotFoundException("Repository root was not found.");
        }

        var pluginRoot = Path.Combine(root.FullName, "plugins", "official-plugin-inspector", "bin");
        foreach (var configuration in new[] { "Release", "Debug" })
        {
            var output = Path.Combine(pluginRoot, configuration, "net10.0");
            if (Directory.Exists(output))
            {
                return output;
            }
        }

        throw new DirectoryNotFoundException(
            $"Official plugin inspector output was not found under '{pluginRoot}'.");
    }

    private sealed class RecordingValidator : IPluginUpgradeValidator
    {
        public int ValidationCount { get; private set; }
        public int MigrationCount { get; private set; }
        public Exception? Failure { get; init; }
        public Exception? MigrationFailure { get; set; }
        public Func<Task>? MigrationAction { get; set; }

        public async Task<PluginMigrationExecutionResult> MigrateAsync(
            PluginPackageInspection inspection,
            string installedDirectory,
            string fromVersion,
            IReadOnlyList<string> grantedCapabilities,
            CancellationToken cancellationToken = default)
        {
            MigrationCount++;
            Assert.True(Directory.Exists(installedDirectory));
            if (MigrationAction is not null)
            {
                await MigrationAction();
            }
            if (MigrationFailure is not null)
            {
                throw MigrationFailure;
            }
            return new PluginMigrationExecutionResult(
                "migrated",
                [new PluginMigrationStepExecution("settings.copy", "completed", 2)]);
        }

        public Task ValidateAsync(
            PluginPackageInspection inspection,
            string installedDirectory,
            IReadOnlyList<string> grantedCapabilities,
            CancellationToken cancellationToken = default)
        {
            ValidationCount++;
            Assert.True(Directory.Exists(installedDirectory));
            Assert.True(File.Exists(Path.Combine(installedDirectory, inspection.EntryPointPath)));
            if (Failure is not null)
            {
                return Task.FromException(Failure);
            }

            return Task.CompletedTask;
        }
    }

}
