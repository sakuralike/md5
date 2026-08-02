using System.Net.Http;
using System.Net.Http.Headers;
using System.Net.Http.Json;
using System.Text.Json;
using PasswordDetective.Desktop.Protocol;

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

    private async Task<TResponse> GetAsync<TResponse>(
        string serverBaseUrl,
        string relativePath,
        CancellationToken cancellationToken)
    {
        using var request = new HttpRequestMessage(
            HttpMethod.Get,
            BuildUri(serverBaseUrl, relativePath));
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
        var normalized = baseUri.AbsoluteUri.EndsWith('/')
            ? baseUri
            : new Uri(baseUri.AbsoluteUri + "/");
        return new Uri(normalized, relativePath);
    }

    public void Dispose()
    {
        if (_ownsClient)
        {
            _httpClient.Dispose();
        }
    }
}

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
