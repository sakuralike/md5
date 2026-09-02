using System.IO;
using System.IO.Compression;
using System.Net;
using System.Net.Sockets;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using PasswordDetective.Desktop.Plugins.Packages;
using PasswordDetective.Desktop.Plugins.Protocol;
using PasswordDetective.Desktop.Plugins.Windows;

namespace PasswordDetective.Desktop.Plugins.DynamicReview;

public sealed record DynamicReviewFinding(
    string Stage,
    string RuleId,
    string Severity,
    string Title,
    string Detail,
    string? FilePath,
    IReadOnlyDictionary<string, object?> Evidence,
    bool Blocked);

public sealed record DynamicReviewExecutionResult(
    string Outcome,
    bool EvidenceComplete,
    bool FreshEnvironment,
    string DestructionProofSha256,
    IReadOnlyDictionary<string, object?> Summary,
    IReadOnlyList<DynamicReviewFinding> Findings,
    string? ErrorCode = null,
    string? ErrorMessage = null);

public sealed class DynamicReviewExecutor
{
    private readonly PluginPackageVerifier _verifier;
    private readonly IWindowsPluginIsolationPolicy _isolationPolicy;

    public DynamicReviewExecutor(PluginPackageVerifier? verifier = null)
        : this(verifier ?? new PluginPackageVerifier(), RequiredWindowsPluginIsolationPolicy.Instance)
    {
    }

    internal DynamicReviewExecutor(
        PluginPackageVerifier verifier,
        IWindowsPluginIsolationPolicy isolationPolicy)
    {
        _verifier = verifier;
        _isolationPolicy = isolationPolicy;
    }

    public async Task<DynamicReviewExecutionResult> ExecuteAsync(
        string packagePath,
        string taskId,
        string workspaceRoot,
        bool freshEnvironment,
        CancellationToken cancellationToken = default)
    {
        var taskDirectory = Path.Combine(workspaceRoot, taskId);
        if (Directory.Exists(taskDirectory))
        {
            return Failed(
                taskId,
                freshEnvironment,
                "dynamic_workspace_reused",
                "动态审核工作目录不是新建的。",
                blocked: false);
        }

        Directory.CreateDirectory(taskDirectory);
        var extractedDirectory = Path.Combine(taskDirectory, "package");
        var runDirectory = Path.Combine(taskDirectory, "run");
        var findings = new List<DynamicReviewFinding>();
        var canaryEnvironmentVariable = "PD_CANARY_SECRET_"
            + Convert.ToHexStringLower(SHA256.HashData(Encoding.UTF8.GetBytes(taskId)))[..16];
        var previousCanaryEnvironmentValue = Environment.GetEnvironmentVariable(canaryEnvironmentVariable);
        Environment.SetEnvironmentVariable(canaryEnvironmentVariable, "dynamic-review-canary");
        var summary = new Dictionary<string, object?>
        {
            ["fresh_environment"] = freshEnvironment,
            ["network_connected"] = false,
            ["child_process_count"] = 0,
        };
        try
        {
            var inspection = await _verifier.VerifyAsync(packagePath, cancellationToken);
            Directory.CreateDirectory(extractedDirectory);
            Directory.CreateDirectory(runDirectory);
            await ExtractVerifiedAsync(packagePath, inspection, extractedDirectory, cancellationToken);
            var executablePath = ResolveContainedPath(extractedDirectory, inspection.EntryPointPath);
            var options = new PluginProcessStartOptions
            {
                PluginId = inspection.Manifest.PluginId,
                ExecutablePath = executablePath,
                WorkingDirectory = runDirectory,
                Arguments = ["--pdpp", "--manifest", Path.Combine(extractedDirectory, PluginPackageVerifier.ManifestPath)],
                MemoryLimitBytes = inspection.Manifest.Limits.MemoryMb * 1024L * 1024,
                ActiveProcessLimit = 1,
                CpuRatePercent = inspection.Manifest.Limits.CpuPercent,
                ReadOnlyDirectories = [extractedDirectory],
                DeleteAppContainerProfileOnDispose = true,
            };

            await using (var host = await StartHostAsync(options, cancellationToken))
            {
                summary["appcontainer"] = host.IsAppContainer;
                if (!host.IsAppContainer)
                {
                    findings.Add(new DynamicReviewFinding(
                        "dynamic_protocol",
                        "PD-DYNAMIC-001",
                        "critical",
                        "插件未运行在 AppContainer",
                        "动态执行器未能确认插件进程处于 AppContainer。",
                        null,
                        new Dictionary<string, object?> { ["appcontainer"] = false },
                        true));
                }

                await host.InitializeAsync(
                    PluginPackageVerifier.HostVersion,
                    inspection.Manifest.Capabilities.Required,
                    TimeSpan.FromSeconds(15),
                    cancellationToken);
                var health = await host.InvokeAsync<object, PdppHealthResult>(
                    PdppProtocol.HealthCheckMethod,
                    new { },
                    TimeSpan.FromSeconds(10),
                    cancellationToken);
                if (!string.Equals(health.Status, "healthy", StringComparison.Ordinal))
                {
                    findings.Add(new DynamicReviewFinding(
                        "dynamic_protocol",
                        "PD-DYNAMIC-002",
                        "high",
                        "插件健康检查未通过",
                        "插件未返回 healthy 状态。",
                        null,
                        new Dictionary<string, object?> { ["healthy"] = false },
                        true));
                }

                summary["protocol_healthy"] = string.Equals(health.Status, "healthy", StringComparison.Ordinal);
                summary["stderr_length"] = host.StandardError.Length;
            }

            await RunDynamicCanariesAsync(
                options,
                inspection.Manifest.Capabilities.Required,
                runDirectory,
                canaryEnvironmentVariable,
                findings,
                summary,
                cancellationToken);

            summary["workspace_deleted"] = false;
            return new DynamicReviewExecutionResult(
                findings.Any(item => item.Blocked) ? "blocked" : "passed",
                EvidenceComplete: true,
                FreshEnvironment: freshEnvironment,
                DestructionProofSha256: ComputeDestructionProof(taskId),
                Summary: summary,
                Findings: findings);
        }
        catch (OperationCanceledException)
        {
            return Failed(taskId, freshEnvironment, "dynamic_cancelled", "动态审核被取消。", blocked: false);
        }
        catch (TimeoutException)
        {
            findings.Add(new DynamicReviewFinding(
                "dynamic_resource",
                "PD-DYNAMIC-003",
                "high",
                "插件动态执行超时",
                "插件未在策略规定时间内完成协议操作。",
                null,
                new Dictionary<string, object?> { ["timeout"] = true },
                true));
            return new DynamicReviewExecutionResult(
                "blocked",
                true,
                freshEnvironment,
                ComputeDestructionProof(taskId),
                summary,
                findings);
        }
        catch (Exception exception) when (exception is PluginPackageException or PdppProtocolException)
        {
            return Failed(taskId, freshEnvironment, "dynamic_protocol_failure", "动态协议执行未通过。", blocked: true);
        }
        catch (Exception)
        {
            return Failed(taskId, freshEnvironment, "dynamic_runner_execution_error", "动态审核执行器暂时不可用。", blocked: false);
        }
        finally
        {
            Environment.SetEnvironmentVariable(canaryEnvironmentVariable, previousCanaryEnvironmentValue);
            TryDeleteDirectory(taskDirectory);
            summary["workspace_deleted"] = !Directory.Exists(taskDirectory);
        }
    }

    private async Task RunDynamicCanariesAsync(
        PluginProcessStartOptions options,
        IReadOnlyList<string> grantedCapabilities,
        string runDirectory,
        string canaryEnvironmentVariable,
        List<DynamicReviewFinding> findings,
        Dictionary<string, object?> summary,
        CancellationToken cancellationToken)
    {
        await RunProbeCanaryAsync(options, grantedCapabilities, runDirectory, findings, summary, cancellationToken);
        await RunEnvironmentCanaryAsync(options, grantedCapabilities, canaryEnvironmentVariable, findings, summary, cancellationToken);
        await RunSpawnCanaryAsync(options, grantedCapabilities, findings, summary, cancellationToken);
        await RunTimeoutCanaryAsync(options, grantedCapabilities, findings, summary, cancellationToken);
        await RunOversizedOutputCanaryAsync(options, grantedCapabilities, findings, summary, cancellationToken);
    }

    private async Task RunProbeCanaryAsync(
        PluginProcessStartOptions options,
        IReadOnlyList<string> grantedCapabilities,
        string runDirectory,
        List<DynamicReviewFinding> findings,
        Dictionary<string, object?> summary,
        CancellationToken cancellationToken)
    {
        var canaryPath = Path.Combine(Path.GetDirectoryName(runDirectory)!, "dynamic-canary.txt");
        await File.WriteAllTextAsync(canaryPath, "dynamic-canary", cancellationToken);
        using var listener = new TcpListener(IPAddress.Loopback, 0);
        listener.Start();
        var port = ((IPEndPoint)listener.LocalEndpoint).Port;
        summary["canary_probe_invoked"] = true;
        var outcome = await InvokeCanaryAsync(
            options,
            grantedCapabilities,
            "probe",
            JsonSerializer.SerializeToElement(new
            {
                file_path = canaryPath,
                host = IPAddress.Loopback.ToString(),
                port,
            }),
            TimeSpan.FromSeconds(5),
            cancellationToken);
        var fileRead = outcome.Result?.TryGetProperty("file_read", out var file) == true && file.GetBoolean();
        var networkConnected = outcome.Result?.TryGetProperty("network_connected", out var network) == true && network.GetBoolean();
        summary["canary_file_read"] = fileRead;
        summary["canary_network_connected"] = networkConnected;
        summary["canary_probe_supported"] = outcome.Supported;
        if (fileRead)
        {
            findings.Add(new DynamicReviewFinding(
                "dynamic_file", "PD-DYNAMIC-010", "critical", "未授权文件读取成功",
                "动态探针确认插件能够读取不应暴露的文件。", null,
                new Dictionary<string, object?> { ["canary"] = "dynamic-canary" }, true));
        }
        if (networkConnected)
        {
            findings.Add(new DynamicReviewFinding(
                "dynamic_network", "PD-DYNAMIC-011", "high", "默认断网环境仍可联网",
                "动态探针确认插件建立了未授权网络连接。", null,
                new Dictionary<string, object?> { ["network"] = true }, true));
        }
    }

    private async Task RunEnvironmentCanaryAsync(
        PluginProcessStartOptions options,
        IReadOnlyList<string> grantedCapabilities,
        string canaryEnvironmentVariable,
        List<DynamicReviewFinding> findings,
        Dictionary<string, object?> summary,
        CancellationToken cancellationToken)
    {
        summary["canary_environment_invoked"] = true;
        var outcome = await InvokeCanaryAsync(
            options,
            grantedCapabilities,
            "environment",
            JsonSerializer.SerializeToElement(canaryEnvironmentVariable),
            TimeSpan.FromSeconds(5),
            cancellationToken);
        var present = outcome.Result?.TryGetProperty("present", out var value) == true && value.GetBoolean();
        summary["canary_secret_visible"] = present;
        summary["canary_environment_supported"] = outcome.Supported;
        if (present)
        {
            findings.Add(new DynamicReviewFinding(
                "dynamic_file", "PD-DYNAMIC-012", "critical", "插件读取到宿主秘密环境变量",
                "动态探针确认插件能够看到宿主秘密环境变量。", null,
                new Dictionary<string, object?> { ["environment_canary"] = true }, true));
        }
    }

    private async Task RunSpawnCanaryAsync(
        PluginProcessStartOptions options,
        IReadOnlyList<string> grantedCapabilities,
        List<DynamicReviewFinding> findings,
        Dictionary<string, object?> summary,
        CancellationToken cancellationToken)
    {
        summary["canary_spawn_child_invoked"] = true;
        try
        {
            var outcome = await InvokeCanaryAsync(
                options,
                grantedCapabilities,
                "spawn-child",
                JsonSerializer.SerializeToElement(new { }),
                TimeSpan.FromSeconds(5),
                cancellationToken);
            var childPid = outcome.Result?.TryGetProperty("child_pid", out var value) == true
                ? value.GetInt32()
                : 0;
            summary["child_process_count"] = childPid > 0 ? 1 : 0;
            summary["canary_spawn_child_supported"] = outcome.Supported;
            if (childPid > 0)
            {
                findings.Add(new DynamicReviewFinding(
                    "dynamic_process", "PD-DYNAMIC-013", "critical", "插件派生子进程",
                    "动态探针确认插件创建了子进程。", null,
                    new Dictionary<string, object?> { ["child_process_observed"] = true }, true));
            }
        }
        catch (PdppProcessExitedException)
        {
            summary["canary_spawn_child_supported"] = true;
            findings.Add(new DynamicReviewFinding(
                "dynamic_process", "PD-DYNAMIC-013", "critical", "插件子进程探测异常退出",
                "插件在子进程探测期间异常退出，无法证明其未尝试派生子进程。", null,
                new Dictionary<string, object?> { ["child_process_probe_exited"] = true }, true));
        }
    }

    private async Task RunTimeoutCanaryAsync(
        PluginProcessStartOptions options,
        IReadOnlyList<string> grantedCapabilities,
        List<DynamicReviewFinding> findings,
        Dictionary<string, object?> summary,
        CancellationToken cancellationToken)
    {
        summary["canary_hang_invoked"] = true;
        try
        {
            var outcome = await InvokeCanaryAsync(
                options,
                grantedCapabilities,
                "hang",
                JsonSerializer.SerializeToElement(new { }),
                TimeSpan.FromSeconds(2),
                cancellationToken);
            summary["canary_hang_supported"] = outcome.Supported;
            summary["timeout_enforced"] = false;
            if (outcome.Supported)
            {
                findings.Add(new DynamicReviewFinding(
                    "dynamic_resource", "PD-DYNAMIC-014", "high", "超时探针未被终止",
                    "插件未在动态审核超时窗口内结束。", null,
                    new Dictionary<string, object?> { ["timeout_enforced"] = false }, true));
            }
        }
        catch (TimeoutException)
        {
            summary["canary_hang_supported"] = true;
            summary["timeout_enforced"] = true;
        }
    }

    private async Task RunOversizedOutputCanaryAsync(
        PluginProcessStartOptions options,
        IReadOnlyList<string> grantedCapabilities,
        List<DynamicReviewFinding> findings,
        Dictionary<string, object?> summary,
        CancellationToken cancellationToken)
    {
        summary["canary_oversized_output_invoked"] = true;
        try
        {
            var outcome = await InvokeCanaryAsync(
                options,
                grantedCapabilities,
                "oversized-output",
                JsonSerializer.SerializeToElement(new { }),
                TimeSpan.FromSeconds(5),
                cancellationToken);
            summary["canary_oversized_output_supported"] = outcome.Supported;
            summary["message_limit_enforced"] = false;
            if (outcome.Supported)
            {
                findings.Add(new DynamicReviewFinding(
                    "dynamic_resource", "PD-DYNAMIC-015", "high", "超大协议响应未被阻断",
                    "插件返回超过协议消息上限的响应。", null,
                    new Dictionary<string, object?> { ["message_limit_enforced"] = false }, true));
            }
        }
        catch (PdppProtocolException)
        {
            summary["canary_oversized_output_supported"] = true;
            summary["message_limit_enforced"] = true;
        }
    }

    private async Task<CanaryCommandOutcome> InvokeCanaryAsync(
        PluginProcessStartOptions options,
        IReadOnlyList<string> grantedCapabilities,
        string command,
        JsonElement input,
        TimeSpan timeout,
        CancellationToken cancellationToken)
    {
        await using var host = await StartHostAsync(options, cancellationToken);
        if (!host.IsAppContainer)
        {
            throw new PdppProtocolException("动态 canary 未运行在 AppContainer。");
        }
        await host.InitializeAsync(
            PluginPackageVerifier.HostVersion,
            grantedCapabilities,
            TimeSpan.FromSeconds(15),
            cancellationToken);
        try
        {
            return new CanaryCommandOutcome(
                Supported: true,
                await host.InvokeAsync<PdppCommandParams, JsonElement>(
                    PdppProtocol.ExecuteCommandMethod,
                    new PdppCommandParams(command, input),
                    timeout,
                    cancellationToken));
        }
        catch (PdppRemoteException exception) when (exception.Code == -32602)
        {
            return new CanaryCommandOutcome(Supported: false, Result: null);
        }
    }

    private sealed record CanaryCommandOutcome(bool Supported, JsonElement? Result);

    private Task<PluginProcessHost> StartHostAsync(
        PluginProcessStartOptions options,
        CancellationToken cancellationToken)
    {
        var backend = Environment.GetEnvironmentVariable("PDPP_SANDBOX_BACKEND");
        if (string.Equals(backend, "rust-host", StringComparison.OrdinalIgnoreCase))
        {
            return PluginProcessHost.StartWithHostSandboxAsync(options, cancellationToken);
        }

        if (string.Equals(backend, "rust", StringComparison.OrdinalIgnoreCase))
        {
            return PluginProcessHost.StartWithRustSandboxAsync(options, cancellationToken);
        }

        return PluginProcessHost.StartWithIsolationPolicyAsync(options, _isolationPolicy, cancellationToken);
    }

    private static DynamicReviewExecutionResult Failed(
        string taskId,
        bool freshEnvironment,
        string errorCode,
        string message,
        bool blocked)
    {
        return new DynamicReviewExecutionResult(
            blocked ? "blocked" : "infrastructure_failed",
            EvidenceComplete: false,
            FreshEnvironment: freshEnvironment,
            DestructionProofSha256: ComputeDestructionProof(taskId),
            Summary: new Dictionary<string, object?>
            {
                ["fresh_environment"] = freshEnvironment,
                ["network_connected"] = false,
            },
            Findings: blocked
                ? [new DynamicReviewFinding(
                    "dynamic_protocol",
                    "PD-DYNAMIC-004",
                    "high",
                    "动态审核协议失败",
                    message,
                    null,
                    new Dictionary<string, object?> { ["failed"] = true },
                    true)]
                : [],
            ErrorCode: errorCode,
            ErrorMessage: message);
    }

    private static async Task ExtractVerifiedAsync(
        string packagePath,
        PluginPackageInspection inspection,
        string destination,
        CancellationToken cancellationToken)
    {
        using var archive = ZipFile.OpenRead(packagePath);
        foreach (var file in inspection.Files)
        {
            cancellationToken.ThrowIfCancellationRequested();
            var entry = archive.GetEntry(file.Path)
                ?? throw new PluginPackageException("动态审核制品条目缺失。");
            var target = ResolveContainedPath(destination, file.Path);
            Directory.CreateDirectory(Path.GetDirectoryName(target)!);
            await using var source = entry.Open();
            await using var output = new FileStream(target, FileMode.CreateNew, FileAccess.Write, FileShare.None);
            await source.CopyToAsync(output, cancellationToken);
        }
    }

    private static string ResolveContainedPath(string root, string relativePath)
    {
        var fullRoot = Path.GetFullPath(root).TrimEnd(Path.DirectorySeparatorChar)
            + Path.DirectorySeparatorChar;
        var fullPath = Path.GetFullPath(
            Path.Combine(root, relativePath.Replace('/', Path.DirectorySeparatorChar)));
        if (!fullPath.StartsWith(fullRoot, StringComparison.OrdinalIgnoreCase))
        {
            throw new PluginPackageException("动态审核路径逃逸工作目录。");
        }

        return fullPath;
    }

    private static void TryDeleteDirectory(string path)
    {
        try
        {
            if (Directory.Exists(path))
            {
                Directory.Delete(path, recursive: true);
            }
        }
        catch (IOException)
        {
        }
        catch (UnauthorizedAccessException)
        {
        }
    }

    private static string ComputeDestructionProof(string taskId) =>
        Convert.ToHexStringLower(
            SHA256.HashData(Encoding.UTF8.GetBytes($"pdpp-dynamic-destroyed-v1\n{taskId}\n")));
}
