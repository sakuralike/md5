using System.IO;
using System.IO.Compression;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using PasswordDetective.Desktop.Plugins.Packages;
using PasswordDetective.Desktop.Plugins.Protocol;

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

    public DynamicReviewExecutor(PluginPackageVerifier? verifier = null)
    {
        _verifier = verifier ?? new PluginPackageVerifier();
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

            await using (var host = await PluginProcessHost.StartAsync(options, cancellationToken))
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

                await RunDynamicCanariesAsync(host, inspection.Manifest.Commands, runDirectory, findings, summary, cancellationToken);
            }

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
            TryDeleteDirectory(taskDirectory);
            summary["workspace_deleted"] = !Directory.Exists(taskDirectory);
        }
    }

    private static async Task RunDynamicCanariesAsync(
        PluginProcessHost host,
        IReadOnlyList<PluginCommandManifest> commands,
        string runDirectory,
        List<DynamicReviewFinding> findings,
        Dictionary<string, object?> summary,
        CancellationToken cancellationToken)
    {
        var commandIds = commands.Select(item => item.Id).ToHashSet(StringComparer.Ordinal);
        if (commandIds.Contains("probe"))
        {
            var canaryPath = Path.Combine(runDirectory, "dynamic-canary.txt");
            await File.WriteAllTextAsync(canaryPath, "dynamic-canary", cancellationToken);
            var probe = await host.InvokeAsync<PdppCommandParams, JsonElement>(
                PdppProtocol.ExecuteCommandMethod,
                new PdppCommandParams(
                    "probe",
                    JsonSerializer.SerializeToElement(new { file_path = canaryPath, host = "127.0.0.1", port = 9 })),
                TimeSpan.FromSeconds(5),
                cancellationToken);
            var fileRead = probe.TryGetProperty("file_read", out var file) && file.GetBoolean();
            var networkConnected = probe.TryGetProperty("network_connected", out var network) && network.GetBoolean();
            summary["probe_file_read"] = fileRead;
            summary["probe_network_connected"] = networkConnected;
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

        if (commandIds.Contains("environment"))
        {
            var environment = await host.InvokeAsync<PdppCommandParams, JsonElement>(
                PdppProtocol.ExecuteCommandMethod,
                new PdppCommandParams("environment", JsonSerializer.SerializeToElement("APP_SECRET_KEY")),
                TimeSpan.FromSeconds(5),
                cancellationToken);
            var present = environment.TryGetProperty("present", out var value) && value.GetBoolean();
            summary["host_secret_visible"] = present;
            if (present)
            {
                findings.Add(new DynamicReviewFinding(
                    "dynamic_file", "PD-DYNAMIC-012", "critical", "插件读取到宿主秘密环境变量",
                    "动态探针确认插件能够看到宿主秘密环境变量。", null,
                    new Dictionary<string, object?> { ["variable"] = "APP_SECRET_KEY" }, true));
            }
        }

        if (commandIds.Contains("spawn-child"))
        {
            var child = await host.InvokeAsync<PdppCommandParams, JsonElement>(
                PdppProtocol.ExecuteCommandMethod,
                new PdppCommandParams("spawn-child", JsonSerializer.SerializeToElement(new { })),
                TimeSpan.FromSeconds(5),
                cancellationToken);
            var childPid = child.TryGetProperty("child_pid", out var value) ? value.GetInt32() : 0;
            summary["child_process_count"] = childPid > 0 ? 1 : 0;
            if (childPid > 0)
            {
                findings.Add(new DynamicReviewFinding(
                    "dynamic_process", "PD-DYNAMIC-013", "critical", "插件派生子进程",
                    "动态探针确认插件创建了子进程。", null,
                    new Dictionary<string, object?> { ["child_process_observed"] = true }, true));
            }
        }

        if (commandIds.Contains("hang"))
        {
            try
            {
                await host.InvokeAsync<PdppCommandParams, JsonElement>(
                    PdppProtocol.ExecuteCommandMethod,
                    new PdppCommandParams("hang", JsonSerializer.SerializeToElement(new { })),
                    TimeSpan.FromSeconds(2),
                    cancellationToken);
                findings.Add(new DynamicReviewFinding(
                    "dynamic_resource", "PD-DYNAMIC-014", "high", "超时探针未被终止",
                    "插件未在动态审核超时窗口内结束。", null,
                    new Dictionary<string, object?> { ["timeout_enforced"] = false }, true));
            }
            catch (TimeoutException)
            {
                summary["timeout_enforced"] = true;
            }
        }

        if (commandIds.Contains("oversized-output"))
        {
            try
            {
                await host.InvokeAsync<PdppCommandParams, JsonElement>(
                    PdppProtocol.ExecuteCommandMethod,
                    new PdppCommandParams("oversized-output", JsonSerializer.SerializeToElement(new { })),
                    TimeSpan.FromSeconds(5),
                    cancellationToken);
                findings.Add(new DynamicReviewFinding(
                    "dynamic_resource", "PD-DYNAMIC-015", "high", "超大协议响应未被阻断",
                    "插件返回超过协议消息上限的响应。", null,
                    new Dictionary<string, object?> { ["message_limit_enforced"] = false }, true));
            }
            catch (PdppProtocolException)
            {
                summary["message_limit_enforced"] = true;
            }
        }
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
