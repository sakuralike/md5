using PasswordDetective.Desktop.Models;

namespace PasswordDetective.Desktop.Services;

public interface IProtectedSessionStore
{
    Task<DesktopSession?> LoadAsync(CancellationToken cancellationToken = default);
    Task SaveAsync(DesktopSession session, CancellationToken cancellationToken = default);
    void Clear();
}
