using System.Text.Json;

namespace PasswordDetective.OfficialHashQuery;

public sealed record HashQueryRequest(string Algorithm, string Digest)
{
    public static HashQueryRequest Parse(JsonElement input)
    {
        if (input.ValueKind != JsonValueKind.Object
            || !input.TryGetProperty("algorithm", out var algorithmElement)
            || algorithmElement.ValueKind != JsonValueKind.String
            || !input.TryGetProperty("digest", out var digestElement)
            || digestElement.ValueKind != JsonValueKind.String)
        {
            throw new InvalidOperationException("必须提供哈希算法和摘要。");
        }

        var algorithm = algorithmElement.GetString()?.Trim().ToLowerInvariant();
        var digest = digestElement.GetString()?.Trim().ToLowerInvariant();
        var expectedLength = algorithm switch
        {
            "md5" => 32,
            "sha1" => 40,
            "sha256" => 64,
            "sha512" => 128,
            _ => 0,
        };
        if (expectedLength == 0
            || digest is null
            || digest.Length != expectedLength
            || digest.Any(character => !Uri.IsHexDigit(character)))
        {
            throw new InvalidOperationException("哈希算法或摘要格式无效。");
        }

        return new HashQueryRequest(algorithm!, digest);
    }
}
