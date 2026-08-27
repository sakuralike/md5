using System.Text.Json;
using System.IO;
using PasswordDetective.Desktop.Plugins;
using PasswordDetective.Desktop.Plugins.Protocol;

namespace PasswordDetective.Desktop.Tests;

public sealed class PdppProtocolTests
{
    [Fact]
    public void EmbeddedSchemaDefinesStrictJsonRpcEnvelopeAndMethods()
    {
        using var schema = PdppProtocol.OpenSchema();
        using var document = JsonDocument.Parse(schema);
        var text = document.RootElement.GetRawText();

        Assert.False(document.RootElement
            .GetProperty("$defs")
            .GetProperty("request")
            .GetProperty("additionalProperties")
            .GetBoolean());
        Assert.Contains(PdppProtocol.InitializeMethod, text);
        Assert.Contains(PdppProtocol.HealthCheckMethod, text);
        Assert.Contains(PdppProtocol.ExecuteCommandMethod, text);
        Assert.Contains(PdppProtocol.ShutdownMethod, text);
        Assert.Contains(PdppProtocol.HostFileDigestMethod, text);
        Assert.Contains(PdppProtocol.HostStorageRemoveMethod, text);
    }

    [Fact]
    public void RequestSerializationUsesPdppV1SnakeCaseContract()
    {
        var request = new PdppRequest<PdppInitializeParams>(
            PdppProtocol.JsonRpcVersion,
            "1",
            PdppProtocol.InitializeMethod,
            new PdppInitializeParams(
                PdppProtocol.ProtocolVersion,
                "0.1.0",
                "synthetic.contract",
                ["command.echo"]));

        var json = JsonSerializer.Serialize(request, PdppProtocol.SerializerOptions);
        using var document = JsonDocument.Parse(json);
        var parameters = document.RootElement.GetProperty("params");

        Assert.Equal("2.0", document.RootElement.GetProperty("jsonrpc").GetString());
        Assert.Equal("1.0", parameters.GetProperty("protocol_version").GetString());
        Assert.Equal("synthetic.contract", parameters.GetProperty("plugin_id").GetString());
    }

    [Fact]
    public async Task FileBrokerUsesOpaqueGrantsAndBoundedChunks()
    {
        var directory = CreateTemporaryDirectory();
        try
        {
            var path = Path.Combine(directory, "synthetic.bin");
            var expected = Enumerable.Range(0, 2 * 1024 * 1024)
                .Select(index => (byte)(index % 251))
                .ToArray();
            await File.WriteAllBytesAsync(path, expected);
            using var broker = new PluginFileBroker(maximumChunkBytes: 64 * 1024, maximumFileBytes: 4 * 1024 * 1024);

            var grant = broker.GrantRead(path);
            var digest = await broker.DigestAsync(grant.GrantId, "sha256");
            var actual = new byte[expected.Length];
            var offset = 0;
            while (offset < actual.Length)
            {
                var chunk = await broker.ReadAsync(grant.GrantId, offset, 64 * 1024);
                chunk.CopyTo(actual, offset);
                offset += chunk.Length;
            }

            Assert.Equal("synthetic.bin", grant.FileName);
            Assert.DoesNotContain(directory, grant.FileName, StringComparison.OrdinalIgnoreCase);
            Assert.Equal(expected, actual);
            Assert.Equal(
                Convert.ToHexStringLower(System.Security.Cryptography.SHA256.HashData(expected)),
                digest);
            await Assert.ThrowsAsync<ArgumentOutOfRangeException>(
                async () => await broker.ReadAsync(grant.GrantId, 0, 64 * 1024 + 1));
            await Assert.ThrowsAsync<UnauthorizedAccessException>(
                async () => await broker.ReadAsync(Guid.NewGuid(), 0, 4096));
            Assert.True(broker.Revoke(grant.GrantId));
            await Assert.ThrowsAsync<UnauthorizedAccessException>(
                async () => await broker.ReadAsync(grant.GrantId, 0, 4096));
            await Assert.ThrowsAsync<UnauthorizedAccessException>(
                async () => await broker.DigestAsync(grant.GrantId, "sha256"));
        }
        finally
        {
            Directory.Delete(directory, recursive: true);
        }
    }

    [Fact]
    public void FileBrokerRejectsFilesAboveConfiguredLimit()
    {
        var directory = CreateTemporaryDirectory();
        try
        {
            var path = Path.Combine(directory, "too-large.bin");
            using (var file = File.Create(path))
            {
                file.SetLength(65 * 1024);
            }

            using var broker = new PluginFileBroker(maximumChunkBytes: 4096, maximumFileBytes: 64 * 1024);
            Assert.Throws<InvalidOperationException>(() => { broker.GrantRead(path); });
        }
        finally
        {
            Directory.Delete(directory, recursive: true);
        }
    }

    private static string CreateTemporaryDirectory()
    {
        var path = Path.Combine(Path.GetTempPath(), "password-detective-pdpp", Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(path);
        return path;
    }
}
