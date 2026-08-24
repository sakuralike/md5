using System.IO;
using System.Text.Json;
using System.Text.Json.Serialization;

namespace PasswordDetective.Desktop.Plugins.Protocol;

public static class PdppProtocol
{
    public const string JsonRpcVersion = "2.0";
    public const string ProtocolVersion = "1.0";
    public const string InitializeMethod = "initialize";
    public const string HealthCheckMethod = "health/check";
    public const string ExecuteCommandMethod = "command/execute";
    public const string ShutdownMethod = "shutdown";
    public const int DefaultMaximumMessageBytes = 1024 * 1024;

    internal const string SchemaResourceName =
        "PasswordDetective.Desktop.Plugins.Protocol.pdpp-v1.schema.json";

    public static JsonSerializerOptions SerializerOptions { get; } = new(JsonSerializerDefaults.Web)
    {
        DefaultIgnoreCondition = JsonIgnoreCondition.WhenWritingNull,
        PropertyNamingPolicy = JsonNamingPolicy.SnakeCaseLower,
        WriteIndented = false,
    };

    public static Stream OpenSchema()
    {
        return typeof(PdppProtocol).Assembly.GetManifestResourceStream(SchemaResourceName)
            ?? throw new InvalidOperationException("PDPP v1 schema resource is missing.");
    }
}

public sealed record PdppRequest<TParams>(
    [property: JsonPropertyName("jsonrpc")] string JsonRpc,
    [property: JsonPropertyName("id")] string Id,
    [property: JsonPropertyName("method")] string Method,
    [property: JsonPropertyName("params")] TParams Params);

public sealed record PdppError(
    [property: JsonPropertyName("code")] int Code,
    [property: JsonPropertyName("message")] string Message,
    [property: JsonPropertyName("data")] JsonElement? Data = null);

public sealed record PdppInitializeParams(
    [property: JsonPropertyName("protocol_version")] string ProtocolVersion,
    [property: JsonPropertyName("host_version")] string HostVersion,
    [property: JsonPropertyName("plugin_id")] string PluginId,
    [property: JsonPropertyName("granted_capabilities")] IReadOnlyList<string> GrantedCapabilities);

public sealed record PdppInitializeResult(
    [property: JsonPropertyName("protocol_version")] string ProtocolVersion,
    [property: JsonPropertyName("plugin_id")] string PluginId,
    [property: JsonPropertyName("plugin_version")] string PluginVersion,
    [property: JsonPropertyName("capabilities")] IReadOnlyList<string> Capabilities);

public sealed record PdppHealthResult(
    [property: JsonPropertyName("status")] string Status);

public sealed record PdppCommandParams(
    [property: JsonPropertyName("command")] string Command,
    [property: JsonPropertyName("input")] JsonElement Input);
