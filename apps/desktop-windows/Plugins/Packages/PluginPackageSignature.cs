using System.Globalization;
using System.Security.Cryptography;
using System.Text;
using Org.BouncyCastle.Crypto.Parameters;
using Org.BouncyCastle.Crypto.Signers;

namespace PasswordDetective.Desktop.Plugins.Packages;

public static class PluginPackageSignature
{
    public const string SignaturePath = "signature.ed25519";
    public static readonly int PublicKeySize = Ed25519PublicKeyParameters.KeySize;
    public static readonly int SignatureSize = Ed25519PrivateKeyParameters.SignatureSize;

    public static byte[] BuildPayload(IEnumerable<PluginPackageFile> files)
    {
        var builder = new StringBuilder("PD-PDPKG-SIGNATURE-V1\n");
        foreach (var file in files
                     .Where(file => !string.Equals(
                         file.Path,
                         SignaturePath,
                         StringComparison.OrdinalIgnoreCase))
                     .OrderBy(file => file.Path, StringComparer.Ordinal))
        {
            builder.Append(file.Path);
            builder.Append('\n');
            builder.Append(file.Length.ToString(CultureInfo.InvariantCulture));
            builder.Append('\n');
            builder.Append(file.Sha256.ToLowerInvariant());
            builder.Append('\n');
        }

        return Encoding.UTF8.GetBytes(builder.ToString());
    }

    public static bool Verify(
        IReadOnlyList<PluginPackageFile> files,
        ReadOnlySpan<byte> publicKey,
        ReadOnlySpan<byte> signature)
    {
        if (publicKey.Length != PublicKeySize || signature.Length != SignatureSize)
        {
            return false;
        }

        var payload = BuildPayload(files);
        var verifier = new Ed25519Signer();
        verifier.Init(forSigning: false, new Ed25519PublicKeyParameters(publicKey.ToArray()));
        verifier.BlockUpdate(payload, 0, payload.Length);
        return verifier.VerifySignature(signature.ToArray());
    }

    public static string Fingerprint(ReadOnlySpan<byte> publicKey) =>
        Convert.ToHexStringLower(SHA256.HashData(publicKey));
}
