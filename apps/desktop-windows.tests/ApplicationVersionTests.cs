using PasswordDetective.Desktop.ViewModels;

namespace PasswordDetective.Desktop.Tests;

public sealed class ApplicationVersionTests
{
    [Fact]
    public void RuntimeVersionDrivesClientRegistrationAndWindowTitle()
    {
        Assert.Equal("1.0.0", ApplicationVersion.Current);
        Assert.Equal(ApplicationVersion.Current, MainWindowViewModel.ClientVersion);

        Assert.Equal("密码侦探社-桌面端 v1.0.0", ApplicationVersion.WindowTitle);
    }
}
