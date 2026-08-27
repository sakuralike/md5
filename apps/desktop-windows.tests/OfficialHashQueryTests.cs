using System.Text.Json;
using PasswordDetective.OfficialHashQuery;

namespace PasswordDetective.Desktop.Tests;

public sealed class OfficialHashQueryTests
{
    [Theory]
    [InlineData("md5", "0123456789abcdef0123456789abcdef")]
    [InlineData("sha1", "0123456789abcdef0123456789abcdef01234567")]
    [InlineData("sha256", "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef")]
    [InlineData("sha512", "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef")]
    public void ValidAlgorithmsAndDigestsAreNormalized(string algorithm, string digest)
    {
        var request = HashQueryRequest.Parse(JsonSerializer.SerializeToElement(new
        {
            algorithm = algorithm.ToUpperInvariant(),
            digest = digest.ToUpperInvariant(),
        }));

        Assert.Equal(algorithm, request.Algorithm);
        Assert.Equal(digest, request.Digest);
    }

    [Fact]
    public void InvalidDigestLengthAndCharactersAreRejected()
    {
        Assert.Throws<InvalidOperationException>(() => HashQueryRequest.Parse(
            JsonSerializer.SerializeToElement(new { algorithm = "sha256", digest = "abcd" })));
        Assert.Throws<InvalidOperationException>(() => HashQueryRequest.Parse(
            JsonSerializer.SerializeToElement(new
            {
                algorithm = "sha256",
                digest = "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdeg",
            })));
    }
}
