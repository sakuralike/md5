namespace PasswordDetective.Desktop.Plugins.Packages;

public sealed class PluginPackageException : Exception
{
    public PluginPackageException(string message) : base(message)
    {
    }

    public PluginPackageException(string message, Exception innerException) : base(message, innerException)
    {
    }
}
