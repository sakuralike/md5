using System.Text.Json;
using System.Text.Json.Serialization;
using PasswordDetective.Desktop.Protocol;
using PasswordDetective.Desktop.Services;

namespace PasswordDetective.Desktop.Plugins.Runtime;

public sealed record PluginBrokerSession(
    string ServerBaseUrl,
    string AccessToken,
    string AccountId);

public interface IPluginApiBroker
{
    Task<JsonElement> CallAsync(
        string pluginSlug,
        string pluginVersion,
        string capability,
        JsonElement parameters,
        CancellationToken cancellationToken = default);
}

public sealed class PluginApiBroker : IPluginApiBroker
{
    private static readonly JsonSerializerOptions JsonOptions = new(JsonSerializerDefaults.Web)
    {
        PropertyNamingPolicy = JsonNamingPolicy.SnakeCaseLower,
        PropertyNameCaseInsensitive = true,
    };

    private readonly DesktopApiClient _apiClient;
    private readonly IInstallationIdentityService _identityService;
    private readonly Func<CancellationToken, Task<PluginBrokerSession>> _sessionProvider;

    public PluginApiBroker(
        DesktopApiClient apiClient,
        IInstallationIdentityService identityService,
        Func<CancellationToken, Task<PluginBrokerSession>> sessionProvider)
    {
        _apiClient = apiClient;
        _identityService = identityService;
        _sessionProvider = sessionProvider;
    }

    public async Task<JsonElement> CallAsync(
        string pluginSlug,
        string pluginVersion,
        string capability,
        JsonElement parameters,
        CancellationToken cancellationToken = default)
    {
        var session = await _sessionProvider(cancellationToken);
        try
        {
            await _apiClient.AuthorizePluginBrokerAsync(
                session.ServerBaseUrl,
                session.AccessToken,
                pluginSlug,
                new PluginBrokerAuthorizationRequest(pluginVersion, capability),
                cancellationToken);

            return capability switch
            {
                "api:profile:read" => await ReadProfileAsync(session, parameters, cancellationToken),
                "api:hash:read" => await ReadHashAsync(session, parameters, cancellationToken),
                "api:verification:submit" => await SubmitVerificationAsync(
                    session,
                    parameters,
                    cancellationToken),
                _ => throw new PdppHostRequestException(-32001, "插件平台 API 能力未获准。"),
            };
        }
        catch (Exception exception) when (exception is DesktopApiException or JsonException)
        {
            throw new PdppHostRequestException(-32004, "插件平台 API 授权或请求未通过。");
        }
    }

    private async Task<JsonElement> ReadProfileAsync(
        PluginBrokerSession session,
        JsonElement parameters,
        CancellationToken cancellationToken)
    {
        EnsureEmpty(parameters);
        var profile = await _apiClient.GetTrustProfileAsync(
            session.ServerBaseUrl,
            session.AccessToken,
            cancellationToken);
        return JsonSerializer.SerializeToElement(profile, JsonOptions);
    }

    private async Task<JsonElement> ReadHashAsync(
        PluginBrokerSession session,
        JsonElement parameters,
        CancellationToken cancellationToken)
    {
        if (parameters.ValueKind != JsonValueKind.Object
            || !TryReadString(parameters, "algorithm", out var algorithm)
            || !TryReadString(parameters, "digest", out var digest)
            || algorithm is not ("md5" or "sha1" or "sha256" or "sha512")
            || digest.Length is < 32 or > 128
            || digest.Any(character => !Uri.IsHexDigit(character)))
        {
            throw new PdppHostRequestException(-32602, "哈希读取参数无效。");
        }

        return await _apiClient.GetPluginHashAsync(
            session.ServerBaseUrl,
            session.AccessToken,
            algorithm,
            digest.ToLowerInvariant(),
            cancellationToken);
    }

    private async Task<JsonElement> SubmitVerificationAsync(
        PluginBrokerSession session,
        JsonElement parameters,
        CancellationToken cancellationToken)
    {
        var request = JsonSerializer.Deserialize<PluginVerificationRequest>(
            parameters.GetRawText(),
            JsonOptions);
        if (request is null
            || string.IsNullOrWhiteSpace(request.CandidateId)
            || string.IsNullOrWhiteSpace(request.FingerprintAlgorithm)
            || string.IsNullOrWhiteSpace(request.FingerprintDigest)
            || string.IsNullOrWhiteSpace(request.CandidateDigest)
            || request.Outcome is not ("success" or "failure")
            || request.ArchiveFormat is not ("zip" or "7z"))
        {
            throw new PdppHostRequestException(-32602, "验证回执参数无效。");
        }

        var identity = await _identityService.GetOrCreateAsync(cancellationToken);
        var challenge = await _apiClient.CreateChallengeAsync(
            session.ServerBaseUrl,
            session.AccessToken,
            new ChallengeRequest(
                identity.InstallationId,
                request.CandidateId,
                request.FingerprintAlgorithm,
                request.FingerprintDigest,
                MainWindowViewModelsClientVersion),
            cancellationToken);
        var verifiedAt = DateTimeOffset.UtcNow;
        var canonical = new DesktopReceiptPayload(
            challenge.ChallengeId,
            challenge.ChallengeNonce,
            identity.InstallationId,
            challenge.AccountId,
            challenge.CandidateId,
            challenge.FingerprintAlgorithm,
            challenge.FingerprintDigest,
            request.CandidateDigest,
            request.Outcome,
            request.ArchiveFormat,
            MainWindowViewModelsClientVersion,
            verifiedAt);
        var signature = await _identityService.SignAsync(
            DesktopReceiptCanonicalizer.Build(canonical),
            cancellationToken);
        var receipt = await _apiClient.SubmitReceiptAsync(
            session.ServerBaseUrl,
            session.AccessToken,
            new ReceiptRequest(
                challenge.ChallengeId,
                challenge.ChallengeNonce,
                identity.InstallationId,
                challenge.AccountId,
                challenge.CandidateId,
                challenge.FingerprintAlgorithm,
                challenge.FingerprintDigest,
                request.CandidateDigest,
                request.Outcome,
                request.ArchiveFormat,
                MainWindowViewModelsClientVersion,
                verifiedAt,
                signature),
            cancellationToken);
        return JsonSerializer.SerializeToElement(receipt, JsonOptions);
    }

    private const string MainWindowViewModelsClientVersion = "0.1.0";

    private static void EnsureEmpty(JsonElement parameters)
    {
        if (parameters.ValueKind != JsonValueKind.Object || parameters.EnumerateObject().Any())
        {
            throw new PdppHostRequestException(-32602, "平台 API 参数必须为空对象。");
        }
    }

    private static bool TryReadString(JsonElement parameters, string name, out string value)
    {
        if (parameters.TryGetProperty(name, out var property)
            && property.ValueKind == JsonValueKind.String)
        {
            value = property.GetString() ?? string.Empty;
            return true;
        }

        value = string.Empty;
        return false;
    }

    private sealed record PluginVerificationRequest(
        [property: JsonPropertyName("candidate_id")] string CandidateId,
        [property: JsonPropertyName("fingerprint_algorithm")] string FingerprintAlgorithm,
        [property: JsonPropertyName("fingerprint_digest")] string FingerprintDigest,
        [property: JsonPropertyName("candidate_digest")] string CandidateDigest,
        [property: JsonPropertyName("outcome")] string Outcome,
        [property: JsonPropertyName("archive_format")] string ArchiveFormat);
}
