using System.Text.Json;
using PasswordDetective.OfficialHashQuery;
using PasswordDetective.Pdpp;

await new OfficialHashQueryPlugin().RunAsync();

internal sealed class OfficialHashQueryPlugin : PdppPlugin
{
    public OfficialHashQueryPlugin() : base(
        "com.passworddetective.official-hash-query",
        "1.0.0",
        ["ui:command", "api:hash:read"])
    {
    }

    protected override async Task<object> ExecuteAsync(
        string command,
        JsonElement input,
        PdppHostClient host,
        CancellationToken cancellationToken)
    {
        if (command != "query")
        {
            throw new InvalidOperationException("未知哈希查询命令。");
        }

        var request = HashQueryRequest.Parse(input);
        var result = await host.ReadHashAsync(
            request.Algorithm,
            request.Digest,
            cancellationToken);
        return new
        {
            query = new { algorithm = request.Algorithm, digest = request.Digest },
            response = result,
        };
    }
}
