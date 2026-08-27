using System.IO;
using System.Net.Http;
using System.Net.Http.Headers;
using System.Net.Http.Json;
using System.Security.Cryptography;
using System.Text.Json;
using System.Text.Json.Serialization;
using PasswordDetective.Desktop.Protocol;
using PasswordDetective.Desktop.Plugins.Market;

namespace PasswordDetective.Desktop.Services;

public sealed class DesktopApiClient : IDesktopApiClient, IDisposable
{
    private static readonly JsonSerializerOptions JsonOptions = new(JsonSerializerDefaults.Web)
    {
        PropertyNamingPolicy = JsonNamingPolicy.SnakeCaseLower,
        DictionaryKeyPolicy = JsonNamingPolicy.SnakeCaseLower,
        PropertyNameCaseInsensitive = true,
    };
    private readonly HttpClient _httpClient;
    private readonly bool _ownsClient;

    public DesktopApiClient(HttpClient? httpClient = null)
    {
        _httpClient = httpClient ?? new HttpClient { Timeout = TimeSpan.FromSeconds(20) };
        _ownsClient = httpClient is null;
    }

    public async Task<bool> TestConnectivityAsync(
        string serverBaseUrl,
        CancellationToken cancellationToken = default)
    {
        await GetAsync<JsonElement>(serverBaseUrl, "health/ready", cancellationToken);
        return true;
    }

    public async Task<DesktopAnnouncementListResponse> GetAnnouncementsAsync(
        string serverBaseUrl,
        CancellationToken cancellationToken = default)
    {
        var refresh = DateTimeOffset.UtcNow.ToUnixTimeMilliseconds();
        using var request = new HttpRequestMessage(
            HttpMethod.Get,
            BuildUri(serverBaseUrl, $"desktop/announcements?limit=10&refresh={refresh}"));
        request.Headers.CacheControl = new CacheControlHeaderValue
        {
            NoCache = true,
            NoStore = true,
        };
        request.Headers.UserAgent.ParseAdd("PasswordDetective-Desktop/0.1.0");
        return await SendAsync<DesktopAnnouncementListResponse>(request, cancellationToken);
    }

    public Task<TrustProfileResponse> GetTrustProfileAsync(
        string serverBaseUrl,
        string accessToken,
        CancellationToken cancellationToken = default) =>
        GetAsync<TrustProfileResponse>(serverBaseUrl, "me/trust-profile", accessToken, cancellationToken);

    public Task<DesktopUpdateCheckResponse> CheckForUpdateAsync(
        string serverBaseUrl,
        string currentVersion,
        string channel,
        string platform,
        string architecture,
        CancellationToken cancellationToken = default)
    {
        var query = string.Join(
            "&",
            $"current_version={Uri.EscapeDataString(currentVersion)}",
            $"channel={Uri.EscapeDataString(channel)}",
            $"platform={Uri.EscapeDataString(platform)}",
            $"architecture={Uri.EscapeDataString(architecture)}");
        return GetAsync<DesktopUpdateCheckResponse>(
            serverBaseUrl,
            $"desktop/updates/check?{query}",
            cancellationToken);
    }

    public Task<MarketPluginCatalogResponse> GetPluginCatalogAsync(
        string serverBaseUrl,
        string? query = null,
        int page = 1,
        int pageSize = 20,
        CancellationToken cancellationToken = default)
    {
        var suffix = "desktop/plugins/catalog?architecture=windows-x64"
                     + "&host_version=0.1.0&protocol_version=1"
                     + $"&page={page}&page_size={pageSize}";
        if (!string.IsNullOrWhiteSpace(query))
        {
            suffix += $"&q={Uri.EscapeDataString(query)}";
        }
        return GetAsync<MarketPluginCatalogResponse>(serverBaseUrl, suffix, cancellationToken);
    }

    public Task<MarketPluginCatalogResponse> GetCanaryPluginCatalogAsync(
        string serverBaseUrl,
        string accessToken,
        string? query = null,
        int page = 1,
        int pageSize = 20,
        CancellationToken cancellationToken = default)
    {
        var suffix = "desktop/plugins/canary/catalog?architecture=windows-x64"
                     + "&host_version=0.1.0&protocol_version=1"
                     + $"&page={page}&page_size={pageSize}";
        if (!string.IsNullOrWhiteSpace(query))
        {
            suffix += $"&q={Uri.EscapeDataString(query)}";
        }
        return GetAsync<MarketPluginCatalogResponse>(
            serverBaseUrl,
            suffix,
            accessToken,
            cancellationToken);
    }

    public Task<MarketPluginDetail> GetPluginDetailAsync(
        string serverBaseUrl,
        string slug,
        CancellationToken cancellationToken = default) =>
        GetAsync<MarketPluginDetail>(
            serverBaseUrl,
            $"desktop/plugins/{Uri.EscapeDataString(slug)}",
            cancellationToken);

    public Task<MarketPluginDetail> GetCanaryPluginDetailAsync(
        string serverBaseUrl,
        string accessToken,
        string slug,
        CancellationToken cancellationToken = default) =>
        GetAsync<MarketPluginDetail>(
            serverBaseUrl,
            $"desktop/plugins/canary/{Uri.EscapeDataString(slug)}",
            accessToken,
            cancellationToken);

    public Task<MarketPluginRevocationList> GetPluginRevocationsAsync(
        string serverBaseUrl,
        CancellationToken cancellationToken = default) =>
        GetAsync<MarketPluginRevocationList>(
            serverBaseUrl,
            "desktop/plugins/revocations",
            cancellationToken);

    public Task<PluginBrokerAuthorizationResponse> AuthorizePluginBrokerAsync(
        string serverBaseUrl,
        string accessToken,
        string pluginSlug,
        PluginBrokerAuthorizationRequest request,
        CancellationToken cancellationToken = default) =>
        PostAsync<PluginBrokerAuthorizationRequest, PluginBrokerAuthorizationResponse>(
            serverBaseUrl,
            $"desktop/plugins/{Uri.EscapeDataString(pluginSlug)}/broker/authorize",
            request,
            accessToken,
            cancellationToken);

    public Task<JsonElement> GetPluginHashAsync(
        string serverBaseUrl,
        string accessToken,
        string algorithm,
        string digest,
        CancellationToken cancellationToken = default) =>
        GetAsync<JsonElement>(
            serverBaseUrl,
            $"archives/search?fingerprint={Uri.EscapeDataString(digest)}&algorithm={Uri.EscapeDataString(algorithm)}",
            accessToken,
            cancellationToken);

    public Task<MarketPluginDownloadTicket> IssuePluginDownloadTicketAsync(
        string serverBaseUrl,
        string slug,
        string semver,
        string architecture,
        CancellationToken cancellationToken = default) =>
        PostAsync<DownloadTicketRequest, MarketPluginDownloadTicket>(
            serverBaseUrl,
            $"desktop/plugins/{Uri.EscapeDataString(slug)}/download-ticket",
            new DownloadTicketRequest(architecture, semver),
            null,
            cancellationToken);

    public Task<MarketPluginDownloadTicket> IssueCanaryPluginDownloadTicketAsync(
        string serverBaseUrl,
        string accessToken,
        string versionId,
        string architecture,
        Guid installationId,
        string signature,
        CancellationToken cancellationToken = default) =>
        PostAsync<PluginCanaryDownloadRequest, MarketPluginDownloadTicket>(
            serverBaseUrl,
            $"admin/plugin-reviews/versions/{Uri.EscapeDataString(versionId)}/canary-download-ticket",
            new PluginCanaryDownloadRequest(architecture, installationId, signature),
            accessToken,
            cancellationToken);

    public async Task DownloadPluginArtifactAsync(
        string downloadUrl,
        string destinationPath,
        string expectedSha256,
        long expectedSizeBytes,
        CancellationToken cancellationToken = default,
        string? accessToken = null,
        Guid? installationId = null,
        string? canarySignature = null)
    {
        using var request = new HttpRequestMessage(HttpMethod.Get, downloadUrl);
        if (!string.IsNullOrWhiteSpace(accessToken))
        {
            request.Headers.Authorization = new AuthenticationHeaderValue("Bearer", accessToken);
        }
        if (installationId.HasValue)
        {
            request.Headers.Add("X-Plugin-Installation-Id", installationId.Value.ToString("D"));
        }
        if (!string.IsNullOrWhiteSpace(canarySignature))
        {
            request.Headers.Add("X-Plugin-Canary-Signature", canarySignature);
        }
        using var response = await _httpClient.SendAsync(
            request,
            HttpCompletionOption.ResponseHeadersRead,
            cancellationToken);
        response.EnsureSuccessStatusCode();
        await using (var source = await response.Content.ReadAsStreamAsync(cancellationToken))
        await using (var destination = new FileStream(
                         destinationPath,
                         FileMode.CreateNew,
                         FileAccess.Write,
                         FileShare.None,
                         bufferSize: 64 * 1024,
                         FileOptions.Asynchronous | FileOptions.SequentialScan))
        {
            await source.CopyToAsync(destination, cancellationToken);
            await destination.FlushAsync(cancellationToken);
        }
        var info = new FileInfo(destinationPath);
        if (info.Length != expectedSizeBytes)
        {
            throw new DesktopApiException(422, "desktop.artifact_size_mismatch", "在线制品大小不一致。");
        }
        await using var verify = new FileStream(destinationPath, FileMode.Open, FileAccess.Read, FileShare.Read);
        var actual = Convert.ToHexStringLower(await SHA256.HashDataAsync(verify, cancellationToken));
        if (!string.Equals(actual, expectedSha256, StringComparison.OrdinalIgnoreCase))
        {
            throw new DesktopApiException(422, "desktop.artifact_hash_mismatch", "在线制品摘要不一致。");
        }
    }

    public async Task RecordPluginInstallEventAsync(
        string serverBaseUrl,
        PluginInstallEventRequest payload,
        string? accessToken = null,
        CancellationToken cancellationToken = default)
    {
        using var request = new HttpRequestMessage(
            HttpMethod.Post,
            BuildUri(serverBaseUrl, "desktop/plugins/install-events"))
        {
            Content = JsonContent.Create(payload, options: JsonOptions),
        };
        request.Headers.Add("Idempotency-Key", payload.EventId);
        if (!string.IsNullOrWhiteSpace(accessToken))
        {
            request.Headers.Authorization = new AuthenticationHeaderValue("Bearer", accessToken);
        }
        request.Headers.UserAgent.ParseAdd("PasswordDetective-Desktop/0.1.0");
        using var response = await _httpClient.SendAsync(request, cancellationToken);
        response.EnsureSuccessStatusCode();
    }

    public Task<TokenResponse> LoginAsync(
        string serverBaseUrl,
        LoginRequest request,
        CancellationToken cancellationToken = default) =>
        PostAsync<LoginRequest, TokenResponse>(
            serverBaseUrl,
            "auth/login",
            request,
            null,
            cancellationToken);

    public Task<TokenResponse> RefreshAsync(
        string serverBaseUrl,
        RefreshRequest request,
        CancellationToken cancellationToken = default) =>
        PostAsync<RefreshRequest, TokenResponse>(
            serverBaseUrl,
            "auth/refresh",
            request,
            null,
            cancellationToken);

    public Task<InstallationResponse> RegisterInstallationAsync(
        string serverBaseUrl,
        string accessToken,
        InstallationRegistrationRequest request,
        CancellationToken cancellationToken = default) =>
        PostAsync<InstallationRegistrationRequest, InstallationResponse>(
            serverBaseUrl,
            "desktop/installations",
            request,
            accessToken,
            cancellationToken);

    public Task<ChallengeResponse> CreateChallengeAsync(
        string serverBaseUrl,
        string accessToken,
        ChallengeRequest request,
        CancellationToken cancellationToken = default) =>
        PostAsync<ChallengeRequest, ChallengeResponse>(
            serverBaseUrl,
            "desktop/challenges",
            request,
            accessToken,
            cancellationToken);

    public Task<ReceiptResponse> SubmitReceiptAsync(
        string serverBaseUrl,
        string accessToken,
        ReceiptRequest request,
        CancellationToken cancellationToken = default) =>
        PostAsync<ReceiptRequest, ReceiptResponse>(
            serverBaseUrl,
            "desktop/receipts",
            request,
            accessToken,
            cancellationToken);

    private Task<TResponse> GetAsync<TResponse>(
        string serverBaseUrl,
        string relativePath,
        CancellationToken cancellationToken) =>
        GetAsync<TResponse>(serverBaseUrl, relativePath, null, cancellationToken);

    private async Task<TResponse> GetAsync<TResponse>(
        string serverBaseUrl,
        string relativePath,
        string? accessToken,
        CancellationToken cancellationToken)
    {
        using var request = new HttpRequestMessage(
            HttpMethod.Get,
            BuildUri(serverBaseUrl, relativePath));
        if (!string.IsNullOrWhiteSpace(accessToken))
        {
            request.Headers.Authorization = new AuthenticationHeaderValue("Bearer", accessToken);
        }
        request.Headers.UserAgent.ParseAdd("PasswordDetective-Desktop/0.1.0");
        return await SendAsync<TResponse>(request, cancellationToken);
    }

    private async Task<TResponse> PostAsync<TRequest, TResponse>(
        string serverBaseUrl,
        string relativePath,
        TRequest payload,
        string? accessToken,
        CancellationToken cancellationToken)
    {
        using var request = new HttpRequestMessage(
            HttpMethod.Post,
            BuildUri(serverBaseUrl, relativePath))
        {
            Content = JsonContent.Create(payload, options: JsonOptions),
        };
        if (!string.IsNullOrWhiteSpace(accessToken))
        {
            request.Headers.Authorization = new AuthenticationHeaderValue("Bearer", accessToken);
        }
        request.Headers.UserAgent.ParseAdd("PasswordDetective-Desktop/0.1.0");

        return await SendAsync<TResponse>(request, cancellationToken);
    }

    private async Task<TResponse> SendAsync<TResponse>(
        HttpRequestMessage request,
        CancellationToken cancellationToken)
    {
        using var response = await _httpClient.SendAsync(request, cancellationToken);
        if (!response.IsSuccessStatusCode)
        {
            ApiErrorBody? error = null;
            try
            {
                error = await response.Content.ReadFromJsonAsync<ApiErrorBody>(
                    JsonOptions,
                    cancellationToken);
            }
            catch (JsonException)
            {
                // Fall through to a stable local error without exposing response bodies.
            }
            throw new DesktopApiException(
                (int)response.StatusCode,
                error?.Code ?? "desktop.remote_error",
                error?.Message ?? "服务端请求失败。",
                error?.Details);
        }

        return await response.Content.ReadFromJsonAsync<TResponse>(JsonOptions, cancellationToken)
            ?? throw new DesktopApiException(
                (int)response.StatusCode,
                "desktop.invalid_response",
                "服务端返回了无效响应。");
    }

    private static Uri BuildUri(string serverBaseUrl, string relativePath)
    {
        if (!Uri.TryCreate(serverBaseUrl, UriKind.Absolute, out var baseUri)
            || baseUri.Scheme is not ("http" or "https"))
        {
            throw new ArgumentException("服务地址必须是有效的 HTTP(S) 地址。", nameof(serverBaseUrl));
        }
        var builder = new UriBuilder(baseUri)
        {
            Query = string.Empty,
            Fragment = string.Empty,
        };
        var path = builder.Path.TrimEnd('/');
        if (!path.EndsWith("/api/v1", StringComparison.OrdinalIgnoreCase))
        {
            path = $"{path}/api/v1";
        }
        builder.Path = $"{path}/";
        return new Uri(builder.Uri, relativePath);
    }

    public void Dispose()
    {
        if (_ownsClient)
        {
            _httpClient.Dispose();
        }
    }
}

public sealed record DownloadTicketRequest(
    [property: JsonPropertyName("architecture")] string Architecture,
    [property: JsonPropertyName("semver")] string Semver);

public sealed record PluginCanaryDownloadRequest(
    [property: JsonPropertyName("architecture")] string Architecture,
    [property: JsonPropertyName("installation_id")] Guid InstallationId,
    [property: JsonPropertyName("signature")] string Signature);

public sealed record PluginInstallEventRequest(
    [property: JsonPropertyName("event_id")] string EventId,
    [property: JsonPropertyName("plugin_slug")] string PluginSlug,
    [property: JsonPropertyName("semver")] string Semver,
    [property: JsonPropertyName("architecture")] string Architecture,
    [property: JsonPropertyName("source")] string Source,
    [property: JsonPropertyName("kind")] string Kind,
    [property: JsonPropertyName("result")] string Result,
    [property: JsonPropertyName("client_version")] string ClientVersion,
    [property: JsonPropertyName("permission_evidence")] PluginPermissionEvidencePayload? PermissionEvidence = null,
    [property: JsonPropertyName("migration_evidence")] PluginMigrationEvidencePayload? MigrationEvidence = null,
    [property: JsonPropertyName("installation_id")] Guid? InstallationId = null,
    [property: JsonPropertyName("evidence_signature")] string? EvidenceSignature = null);

public sealed record PluginPermissionEvidencePayload(
    [property: JsonPropertyName("requested_capabilities")] IReadOnlyList<string> RequestedCapabilities,
    [property: JsonPropertyName("approved_capabilities")] IReadOnlyList<string> ApprovedCapabilities,
    [property: JsonPropertyName("granted_capabilities")] IReadOnlyList<string> GrantedCapabilities,
    [property: JsonPropertyName("publisher_key_fingerprint")] string PublisherKeyFingerprint,
    [property: JsonPropertyName("risk_tier")] string RiskTier,
    [property: JsonPropertyName("consented_at")] DateTimeOffset ConsentedAt);

public sealed record PluginMigrationEvidencePayload(
    [property: JsonPropertyName("from_version")] string FromVersion,
    [property: JsonPropertyName("to_version")] string ToVersion,
    [property: JsonPropertyName("status")] string Status,
    [property: JsonPropertyName("started_at")] DateTimeOffset StartedAt,
    [property: JsonPropertyName("completed_at")] DateTimeOffset? CompletedAt,
    [property: JsonPropertyName("steps")] IReadOnlyList<PluginMigrationStepEvidencePayload> Steps);

public sealed record PluginMigrationStepEvidencePayload(
    [property: JsonPropertyName("step_id")] string StepId,
    [property: JsonPropertyName("status")] string Status,
    [property: JsonPropertyName("attempt_count")] int AttemptCount);

public sealed class DesktopApiException(
    int statusCode,
    string code,
    string message,
    IReadOnlyDictionary<string, JsonElement>? details = null) : Exception(message)
{
    public int StatusCode { get; } = statusCode;
    public string Code { get; } = code;
    public IReadOnlyDictionary<string, JsonElement> Details { get; } =
        details ?? new Dictionary<string, JsonElement>();

    public string? GetStringDetail(string key) =>
        Details.TryGetValue(key, out var value) && value.ValueKind == JsonValueKind.String
            ? value.GetString()
            : null;
}
