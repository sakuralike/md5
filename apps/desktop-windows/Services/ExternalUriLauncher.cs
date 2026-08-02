using System.Diagnostics;

namespace PasswordDetective.Desktop.Services;

public interface IExternalUriLauncher
{
    void Open(Uri uri);
}

public sealed class ExternalUriLauncher : IExternalUriLauncher
{
    public void Open(Uri uri)
    {
        if (uri.Scheme is not ("http" or "https"))
        {
            throw new InvalidOperationException("升级地址必须使用 HTTP(S)。");
        }
        Process.Start(new ProcessStartInfo(uri.AbsoluteUri) { UseShellExecute = true });
    }
}
