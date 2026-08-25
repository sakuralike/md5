using System.Net.Http.Headers;
using System.Net.Http.Json;
using System.Security.Cryptography.X509Certificates;
using System.Text.Json.Serialization;
using PasswordDetective.Desktop.Plugins.DynamicReview;

var baseUrl = Required("PLUGIN_RUNNER_BASE_URL").TrimEnd('/') + "/";
var runnerId = Required("PLUGIN_RUNNER_ID");
var runnerSecret = Required("PLUGIN_RUNNER_SECRET");
var certificateFingerprint = Required("PLUGIN_RUNNER_CERTIFICATE_SHA256").ToLowerInvariant();
var architecture = Environment.GetEnvironmentVariable("PLUGIN_RUNNER_ARCHITECTURE")?.Trim()
    is "windows-arm64" ? "windows-arm64" : "windows-x64";
var imageDigest = Required("PLUGIN_RUNNER_IMAGE_SHA256");
var probeVersion = Environment.GetEnvironmentVariable("PLUGIN_RUNNER_PROBE_VERSION")?.Trim()
    ?? "pdpp-dynamic-runner-v1";
var freshEnvironment = Environment.GetEnvironmentVariable("PLUGIN_RUNNER_FRESH_ENVIRONMENT") == "1";
var workspaceRoot = Path.Combine(
    Environment.GetEnvironmentVariable("PLUGIN_RUNNER_WORKSPACE") ?? Path.GetTempPath(),
    "password-detective-plugin-review",
    runnerId);
Directory.CreateDirectory(workspaceRoot);

using var handler = new HttpClientHandler();
var pfxPath = Environment.GetEnvironmentVariable("PLUGIN_RUNNER_CLIENT_CERT_PFX");
if (string.IsNullOrWhiteSpace(pfxPath))
{
    throw new InvalidOperationException("PLUGIN_RUNNER_CLIENT_CERT_PFX is required for mTLS.");
}
if (!string.IsNullOrWhiteSpace(pfxPath))
{
    handler.ClientCertificates.Add(X509CertificateLoader.LoadPkcs12FromFile(
        pfxPath,
        Environment.GetEnvironmentVariable("PLUGIN_RUNNER_CLIENT_CERT_PASSWORD"),
        X509KeyStorageFlags.EphemeralKeySet));
}

using var client = new HttpClient(handler) { BaseAddress = new Uri(baseUrl) };
client.DefaultRequestHeaders.Authorization = new AuthenticationHeaderValue("Bearer", runnerSecret);
client.DefaultRequestHeaders.Add("X-Plugin-Runner-Id", runnerId);
client.DefaultRequestHeaders.Add("X-Plugin-Runner-Certificate-SHA256", certificateFingerprint);
client.DefaultRequestHeaders.Add("X-Client-Certificate-Verified", "SUCCESS");
var executor = new DynamicReviewExecutor();
var once = args.Contains("--once", StringComparer.Ordinal);

do
{
    await HeartbeatAsync();
    var lease = await LeaseAsync();
    if (lease is null)
    {
        if (once)
        {
            return 0;
        }

        await Task.Delay(TimeSpan.FromSeconds(5));
        continue;
    }

    var packagePath = Path.Combine(workspaceRoot, $"{lease.TaskId}.pdpkg");
    try
    {
        await DownloadAsync(lease, packagePath);
        var result = await executor.ExecuteAsync(
            packagePath,
            lease.TaskId,
            workspaceRoot,
            freshEnvironment);
        await CompleteAsync(lease, result);
    }
    catch (Exception)
    {
        await CompleteInfrastructureFailureAsync(lease);
    }
    finally
    {
        TryDelete(packagePath);
    }
}
while (!once);

return 0;

string Required(string name) =>
    Environment.GetEnvironmentVariable(name)?.Trim()
    ?? throw new InvalidOperationException($"Missing required runner setting: {name}");

async Task HeartbeatAsync()
{
    using var response = await client.PostAsJsonAsync(
        "api/v1/plugin-runner/heartbeat",
        new
        {
            policy_version = "desktop-plugin-dynamic-review-v1",
            image_digest = imageDigest,
            probe_version = probeVersion,
            fresh_environment_ready = freshEnvironment,
        });
    response.EnsureSuccessStatusCode();
}

async Task<RunnerLease?> LeaseAsync()
{
    using var response = await client.PostAsync("api/v1/plugin-runner/tasks/lease", null);
    response.EnsureSuccessStatusCode();
    return await response.Content.ReadFromJsonAsync<RunnerLease>();
}

async Task DownloadAsync(RunnerLease lease, string destination)
{
    using var request = new HttpRequestMessage(HttpMethod.Get, lease.ArtifactUrl);
    request.Headers.Add("X-Plugin-Task-Token", lease.TaskToken);
    using var response = await client.SendAsync(request, HttpCompletionOption.ResponseHeadersRead);
    response.EnsureSuccessStatusCode();
    await using var source = await response.Content.ReadAsStreamAsync();
    await using var target = new FileStream(destination, FileMode.CreateNew, FileAccess.Write, FileShare.None);
    await source.CopyToAsync(target);
}

async Task CompleteAsync(RunnerLease lease, DynamicReviewExecutionResult result)
{
    using var request = new HttpRequestMessage(
        HttpMethod.Post,
        $"api/v1/plugin-runner/tasks/{lease.TaskId}/complete");
    request.Headers.Add("X-Plugin-Task-Token", lease.TaskToken);
    request.Content = JsonContent.Create(new
    {
        outcome = result.Outcome,
        evidence_complete = result.EvidenceComplete,
        fresh_environment = result.FreshEnvironment,
        destruction_proof_sha256 = result.DestructionProofSha256,
        summary = result.Summary,
        findings = result.Findings.Select(item => new
        {
            stage = item.Stage,
            rule_id = item.RuleId,
            severity = item.Severity,
            title = item.Title,
            detail = item.Detail,
            file_path = item.FilePath,
            evidence = item.Evidence,
            blocked = item.Blocked,
        }),
        error_code = result.ErrorCode,
        error_message = result.ErrorMessage,
    });
    using var response = await client.SendAsync(request);
    response.EnsureSuccessStatusCode();
}

async Task CompleteInfrastructureFailureAsync(RunnerLease lease)
{
    using var request = new HttpRequestMessage(
        HttpMethod.Post,
        $"api/v1/plugin-runner/tasks/{lease.TaskId}/complete");
    request.Headers.Add("X-Plugin-Task-Token", lease.TaskToken);
    request.Content = JsonContent.Create(new
    {
        outcome = "infrastructure_failed",
        evidence_complete = false,
        fresh_environment = freshEnvironment,
        destruction_proof_sha256 = Convert.ToHexStringLower(
            System.Security.Cryptography.SHA256.HashData(
                System.Text.Encoding.UTF8.GetBytes($"runner-failure\n{lease.TaskId}\n"))),
        summary = new { runner_error = true },
        findings = Array.Empty<object>(),
        error_code = "runner_execution_error",
        error_message = "动态审核执行器未能完成任务。",
    });
    using var response = await client.SendAsync(request);
    response.EnsureSuccessStatusCode();
}

static void TryDelete(string path)
{
    try
    {
        if (File.Exists(path))
        {
            File.Delete(path);
        }
    }
    catch (IOException)
    {
    }
    catch (UnauthorizedAccessException)
    {
    }
}

sealed record RunnerLease(
    [property: JsonPropertyName("task_id")] string TaskId,
    [property: JsonPropertyName("artifact_url")] string ArtifactUrl,
    [property: JsonPropertyName("task_token")] string TaskToken);
