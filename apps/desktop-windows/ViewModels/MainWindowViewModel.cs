using System.ComponentModel;
using System.IO;
using System.Runtime.CompilerServices;
using System.Runtime.InteropServices;
using System.Security.Cryptography;
using System.Text;
using Microsoft.Win32;
using PasswordDetective.Desktop.Infrastructure;
using PasswordDetective.Desktop.Models;
using PasswordDetective.Desktop.Protocol;
using PasswordDetective.Desktop.Services;

namespace PasswordDetective.Desktop.ViewModels;

public sealed class MainWindowViewModel : INotifyPropertyChanged
{
    private const string ClientVersion = "0.1.0";
    private readonly IFileFingerprintService _fingerprintService;
    private readonly IArchiveVerificationService _archiveVerificationService;
    private readonly IInstallationIdentityService _identityService;
    private readonly IDesktopApiClient _apiClient;
    private readonly IProtectedSessionStore _sessionStore;
    private readonly IExternalUriLauncher _externalUriLauncher;
    private CancellationTokenSource? _cancellation;
    private DesktopSession? _session;
    private InstallationIdentity? _identity;
    private string _selectedFile = string.Empty;
    private string _candidatePassword = string.Empty;
    private string _loginPassword = string.Empty;
    private string _serverBaseUrl = "http://localhost:8000/api/v1/";
    private string _loginName = string.Empty;
    private string _totpCode = string.Empty;
    private string _candidateId = string.Empty;
    private string _status = "请选择 ZIP 或 7z 文件。文件内容和候选密码不会上传。";
    private string _installationStatus = "正在初始化本机安装身份…";
    private string _accountStatus = "未登录";
    private double _progress;
    private bool _isBusy;
    private bool _canRegenerateInstallation;
    private string _upgradeNotice = string.Empty;
    private string _updateStatus = "正在检查稳定通道更新…";
    private string? _updateDownloadUrl;
    private FileFingerprintResult? _result;
    private ArchiveVerificationResult? _verificationResult;

    public MainWindowViewModel(
        IFileFingerprintService fingerprintService,
        IArchiveVerificationService archiveVerificationService,
        IInstallationIdentityService identityService,
        IDesktopApiClient apiClient,
        IProtectedSessionStore sessionStore,
        IExternalUriLauncher externalUriLauncher)
    {
        _fingerprintService = fingerprintService;
        _archiveVerificationService = archiveVerificationService;
        _identityService = identityService;
        _apiClient = apiClient;
        _sessionStore = sessionStore;
        _externalUriLauncher = externalUriLauncher;
        SelectFileCommand = new RelayCommand(SelectFile, () => !IsBusy);
        CalculateCommand = new AsyncRelayCommand(CalculateAsync, CanUseFile);
        VerifyCommand = new AsyncRelayCommand(VerifyAsync, CanVerify);
        LoginCommand = new AsyncRelayCommand(LoginAsync, CanLogin);
        SubmitReceiptCommand = new AsyncRelayCommand(VerifyAndSubmitAsync, CanSubmit);
        RegenerateInstallationCommand = new AsyncRelayCommand(
            RegenerateInstallationAsync,
            () => !IsBusy && CanRegenerateInstallation);
        LogoutCommand = new RelayCommand(Logout, () => !IsBusy && _session is not null);
        CancelCommand = new RelayCommand(Cancel, () => IsBusy);
        CheckForUpdatesCommand = new AsyncRelayCommand(CheckForUpdatesAsync, CanCheckForUpdates);
        OpenUpdateDownloadCommand = new RelayCommand(OpenUpdateDownload, CanOpenUpdateDownload);
        _ = InitializeAsync();
    }

    public string SelectedFile { get => _selectedFile; private set { SetField(ref _selectedFile, value); NotifyCommands(); } }
    public string ServerBaseUrl { get => _serverBaseUrl; set { SetField(ref _serverBaseUrl, value); NotifyCommands(); } }
    public string LoginName { get => _loginName; set { SetField(ref _loginName, value); NotifyCommands(); } }
    public string TotpCode { get => _totpCode; set => SetField(ref _totpCode, value); }
    public string CandidateId { get => _candidateId; set { SetField(ref _candidateId, value); NotifyCommands(); } }
    public string Status { get => _status; private set => SetField(ref _status, value); }
    public string InstallationStatus { get => _installationStatus; private set => SetField(ref _installationStatus, value); }
    public string AccountStatus { get => _accountStatus; private set => SetField(ref _accountStatus, value); }
    public double Progress { get => _progress; private set => SetField(ref _progress, value); }
    public FileFingerprintResult? Result { get => _result; private set => SetField(ref _result, value); }
    public ArchiveVerificationResult? VerificationResult { get => _verificationResult; private set => SetField(ref _verificationResult, value); }
    public bool IsBusy { get => _isBusy; private set { SetField(ref _isBusy, value); NotifyCommands(); } }
    public bool CanRegenerateInstallation { get => _canRegenerateInstallation; private set { SetField(ref _canRegenerateInstallation, value); NotifyCommands(); } }
    public string UpgradeNotice { get => _upgradeNotice; private set => SetField(ref _upgradeNotice, value); }
    public string UpdateStatus { get => _updateStatus; private set => SetField(ref _updateStatus, value); }
    public bool HasUpdate => _updateDownloadUrl is not null;

    public RelayCommand SelectFileCommand { get; }
    public AsyncRelayCommand CalculateCommand { get; }
    public AsyncRelayCommand VerifyCommand { get; }
    public AsyncRelayCommand LoginCommand { get; }
    public AsyncRelayCommand SubmitReceiptCommand { get; }
    public AsyncRelayCommand RegenerateInstallationCommand { get; }
    public RelayCommand LogoutCommand { get; }
    public RelayCommand CancelCommand { get; }
    public AsyncRelayCommand CheckForUpdatesCommand { get; }
    public RelayCommand OpenUpdateDownloadCommand { get; }

    public void SetCandidatePassword(string password) { _candidatePassword = password; NotifyCommands(); }
    public void SetLoginPassword(string password) { _loginPassword = password; NotifyCommands(); }

    private async Task InitializeAsync()
    {
        try
        {
            _identity = await _identityService.GetOrCreateAsync();
            UpdateInstallationStatus(_identity);
            _session = await _sessionStore.LoadAsync();
            if (_session is not null)
            {
                ServerBaseUrl = _session.ServerBaseUrl;
                try
                {
                    await EnsureSessionAndRegistrationAsync(CancellationToken.None);
                }
                catch (DesktopApiException exception)
                {
                    AccountStatus = $"已加载 {_session.Username} 的本地会话，但安装注册需要处理";
                    ApplyApiError("恢复登录状态失败", exception);
                }
            }
        }
        catch (Exception)
        {
            _session = null;
            AccountStatus = "未登录或本地会话已失效";
        }
        finally
        {
            try
            {
                await CheckForUpdatesCoreAsync(CancellationToken.None);
            }
            catch
            {
                UpdateStatus = "暂时无法连接后端更新通道，可稍后手动重试。";
            }
            NotifyCommands();
        }
    }

    private async Task CheckForUpdatesAsync()
    {
        BeginOperation("正在检查桌面端稳定通道更新…");
        try
        {
            await CheckForUpdatesCoreAsync(_cancellation!.Token);
            Status = UpdateStatus;
        }
        catch (OperationCanceledException)
        {
            Status = "检查更新已取消。";
        }
        catch (DesktopApiException exception)
        {
            Status = $"检查更新失败：{exception.Message}";
            UpdateStatus = "后端更新通道暂不可用。";
        }
        catch (Exception)
        {
            Status = "检查更新失败，请确认服务地址与网络连接。";
            UpdateStatus = "后端更新通道暂不可用。";
        }
        finally
        {
            EndOperation();
        }
    }

    private async Task CheckForUpdatesCoreAsync(CancellationToken cancellationToken)
    {
        _updateDownloadUrl = null;
        OnPropertyChanged(nameof(HasUpdate));
        NotifyCommands();
        var architecture = RuntimeInformation.ProcessArchitecture == Architecture.Arm64
            ? "arm64"
            : "x64";
        var update = await _apiClient.CheckForUpdateAsync(
            ServerBaseUrl,
            ClientVersion,
            "stable",
            "windows",
            architecture,
            cancellationToken);
        if (!update.UpdateAvailable)
        {
            UpdateStatus = $"当前版本 {ClientVersion} 已是稳定通道最新版本。";
        }
        else
        {
            if (!Uri.TryCreate(update.DownloadUrl, UriKind.Absolute, out var downloadUri)
                || downloadUri.Scheme is not ("http" or "https"))
            {
                throw new InvalidOperationException("后端返回了无效的 HTTP(S) 升级地址。");
            }
            _updateDownloadUrl = downloadUri.AbsoluteUri;
            var requirement = update.Mandatory ? "必须升级" : "可升级";
            var integrity = update.ArtifactIntegrity == "sha256-verified"
                && update.DistributionAuthorized is true
                ? "SHA-256 完整性和分发授权已登记"
                : "请核对制品完整性与来源";
            UpdateStatus =
                $"发现 {update.LatestVersion}（{requirement}，{integrity}）。{update.ReleaseNotes}";
        }
        OnPropertyChanged(nameof(HasUpdate));
        NotifyCommands();
    }

    private void OpenUpdateDownload()
    {
        if (_updateDownloadUrl is null
            || !Uri.TryCreate(_updateDownloadUrl, UriKind.Absolute, out var uri))
        {
            Status = "升级下载地址无效，请重新检查更新。";
            return;
        }
        try
        {
            _externalUriLauncher.Open(uri);
            Status = "已在系统浏览器中打开后端升级下载入口；安装前请核对下载页展示的 SHA-256。";
        }
        catch (Exception)
        {
            Status = "无法打开系统浏览器，请重新检查更新或联系管理员。";
        }
    }

    private bool CanCheckForUpdates() => !IsBusy && !string.IsNullOrWhiteSpace(ServerBaseUrl);
    private bool CanOpenUpdateDownload() => !IsBusy && _updateDownloadUrl is not null;

    private async Task LoginAsync()
    {
        BeginOperation("正在登录并注册本机安装公钥…");
        try
        {
            var tokens = await _apiClient.LoginAsync(
                ServerBaseUrl,
                new LoginRequest(LoginName.Trim(), _loginPassword, EmptyToNull(TotpCode)),
                _cancellation!.Token);
            _session = ToSession(ServerBaseUrl, tokens);
            await _sessionStore.SaveAsync(_session, _cancellation.Token);
            AccountStatus = $"已登录：{_session.Username} · 正在注册安装身份";
            await RegisterInstallationAsync(_session, _cancellation.Token);
            AccountStatus = $"已登录：{_session.Username} · 令牌由 Windows DPAPI 保护";
            Status = "登录成功，本机安装公钥已注册。";
        }
        catch (DesktopApiException exception)
        {
            ApplyApiError("登录或安装注册失败", exception);
        }
        catch (Exception)
        {
            Status = "登录或安装注册失败，请检查服务地址与网络连接。";
        }
        finally
        {
            EndOperation();
        }
    }

    private async Task VerifyAndSubmitAsync()
    {
        BeginOperation("正在获取一次性挑战并执行本地验证…");
        VerificationResult = null;
        var password = _candidatePassword;
        byte[]? passwordBytes = null;
        try
        {
            var session = await EnsureSessionAndRegistrationAsync(_cancellation!.Token);
            if (Result is null)
            {
                await CalculateFingerprintCoreAsync(_cancellation.Token);
            }
            var challenge = await _apiClient.CreateChallengeAsync(
                session.ServerBaseUrl,
                session.AccessToken,
                new ChallengeRequest(
                    _identity!.InstallationId,
                    CandidateId.Trim(),
                    "sha256",
                    Result!.Sha256,
                    ClientVersion),
                _cancellation.Token);

            VerificationResult = await _archiveVerificationService.VerifyAsync(
                SelectedFile,
                password,
                _cancellation.Token);
            passwordBytes = Encoding.UTF8.GetBytes(password);
            var candidateDigest = Convert.ToHexString(SHA256.HashData(passwordBytes)).ToLowerInvariant();
            var verifiedAt = DateTimeOffset.UtcNow;
            var outcome = VerificationResult.Success ? "success" : "failure";
            var canonicalPayload = new DesktopReceiptPayload(
                challenge.ChallengeId,
                challenge.ChallengeNonce,
                _identity.InstallationId,
                challenge.AccountId,
                challenge.CandidateId,
                challenge.FingerprintAlgorithm,
                challenge.FingerprintDigest,
                candidateDigest,
                outcome,
                VerificationResult.ArchiveFormat,
                ClientVersion,
                verifiedAt);
            var signature = await _identityService.SignAsync(
                DesktopReceiptCanonicalizer.Build(canonicalPayload),
                _cancellation.Token);
            var receipt = await _apiClient.SubmitReceiptAsync(
                session.ServerBaseUrl,
                session.AccessToken,
                new ReceiptRequest(
                    challenge.ChallengeId,
                    challenge.ChallengeNonce,
                    _identity.InstallationId,
                    challenge.AccountId,
                    challenge.CandidateId,
                    challenge.FingerprintAlgorithm,
                    challenge.FingerprintDigest,
                    candidateDigest,
                    outcome,
                    VerificationResult.ArchiveFormat,
                    ClientVersion,
                    verifiedAt,
                    signature),
                _cancellation.Token);
            Status = $"签名回执已接受：{receipt.Outcome}，候选状态 {receipt.CandidateStatus}。";
        }
        catch (OperationCanceledException)
        {
            Status = "验证与回执提交已取消。";
        }
        catch (DesktopApiException exception)
        {
            ApplyApiError("服务端拒绝回执", exception);
        }
        catch (Exception)
        {
            Status = "验证或回执提交失败；文件内容未上传，可检查网络后重试。";
        }
        finally
        {
            if (passwordBytes is not null) CryptographicOperations.ZeroMemory(passwordBytes);
            password = string.Empty;
            EndOperation();
        }
    }

    private async Task<DesktopSession> EnsureSessionAndRegistrationAsync(CancellationToken cancellationToken)
    {
        var session = _session ?? throw new InvalidOperationException("请先登录。 ");
        if (session.ExpiresAt <= DateTimeOffset.UtcNow.AddSeconds(30))
        {
            var tokens = await _apiClient.RefreshAsync(
                session.ServerBaseUrl,
                new RefreshRequest(session.RefreshToken),
                cancellationToken);
            session = ToSession(session.ServerBaseUrl, tokens);
            _session = session;
            await _sessionStore.SaveAsync(session, cancellationToken);
        }
        await RegisterInstallationAsync(session, cancellationToken);
        AccountStatus = $"已登录：{session.Username} · 令牌由 Windows DPAPI 保护";
        return session;
    }

    private async Task RegisterInstallationAsync(DesktopSession session, CancellationToken cancellationToken)
    {
        _identity ??= await _identityService.GetOrCreateAsync(cancellationToken);
        var registration = await _apiClient.RegisterInstallationAsync(
            session.ServerBaseUrl,
            session.AccessToken,
            new InstallationRegistrationRequest(
                _identity.InstallationId,
                _identity.PublicKey,
                _identity.KeyAlgorithm,
                ClientVersion),
            cancellationToken);
        ClearRecoveryState();
        InstallationStatus =
            $"安装实例 {_identity.InstallationId:D} · 服务端状态 {registration.Status} · 已接收回执 {registration.ReceiptCount}";
    }

    private async Task RegenerateInstallationAsync()
    {
        BeginOperation("正在生成新的本机安装身份…");
        try
        {
            _identity = await _identityService.RegenerateAsync(_cancellation!.Token);
            ClearRecoveryState();
            UpdateInstallationStatus(_identity);
            if (_session is null)
            {
                Status = "新的安装身份已生成。登录后将自动向服务端注册。";
                return;
            }

            await EnsureSessionAndRegistrationAsync(_cancellation.Token);
            Status = "新的安装身份已生成并完成服务端注册。";
        }
        catch (OperationCanceledException)
        {
            Status = "重新生成安装身份已取消。";
        }
        catch (DesktopApiException exception)
        {
            ApplyApiError("重新注册安装身份失败", exception);
        }
        catch (Exception)
        {
            Status = "重新生成安装身份失败，请检查当前 Windows 用户的数据保护状态后重试。";
        }
        finally
        {
            EndOperation();
        }
    }

    private void ApplyApiError(string context, DesktopApiException exception)
    {
        var advice = DesktopRecoveryAdvisor.From(exception);
        CanRegenerateInstallation = advice.CanRegenerateInstallation;
        UpgradeNotice = advice.UpgradeRequired ? advice.Message : string.Empty;
        Status = $"{context}：{advice.Message}";
    }

    private void ClearRecoveryState()
    {
        CanRegenerateInstallation = false;
        UpgradeNotice = string.Empty;
    }

    private void UpdateInstallationStatus(InstallationIdentity identity)
    {
        InstallationStatus =
            $"安装实例 {identity.InstallationId:D} · 公钥指纹 {identity.PublicKeyFingerprint[..16]}…";
    }

    private void Logout()
    {
        _sessionStore.Clear();
        _session = null;
        AccountStatus = "未登录";
        Status = "本地令牌已清除。";
        NotifyCommands();
    }

    private void SelectFile()
    {
        var dialog = new OpenFileDialog { Title = "选择压缩包", Filter = "支持的压缩包 (*.zip;*.7z)|*.zip;*.7z", CheckFileExists = true };
        if (dialog.ShowDialog() == true)
        {
            SelectedFile = dialog.FileName;
            Result = null;
            VerificationResult = null;
            Progress = 0;
            Status = "文件已选择，可执行本地验证或登录后提交签名回执。";
        }
    }

    private async Task CalculateAsync() => await RunLocalAsync(calculateOnly: true);
    private async Task VerifyAsync() => await RunLocalAsync(calculateOnly: false);

    private async Task RunLocalAsync(bool calculateOnly)
    {
        BeginOperation(calculateOnly ? "正在计算本地指纹…" : "正在执行本地压缩包验证…");
        try
        {
            if (calculateOnly || Result is null) await CalculateFingerprintCoreAsync(_cancellation!.Token);
            if (!calculateOnly)
            {
                VerificationResult = await _archiveVerificationService.VerifyAsync(SelectedFile, _candidatePassword, _cancellation!.Token);
                Status = VerificationResult.Message;
            }
            else Status = "指纹计算完成；未上传任何文件内容。";
        }
        catch (OperationCanceledException) { Status = "本地操作已取消。"; }
        catch (Exception) { Status = "本地操作失败，请确认文件可读后重试。"; }
        finally { EndOperation(); }
    }

    private async Task CalculateFingerprintCoreAsync(CancellationToken cancellationToken)
    {
        var progress = new Progress<double>(value => Progress = value * 100);
        Result = await _fingerprintService.CalculateAsync(SelectedFile, progress, cancellationToken);
    }

    private bool CanUseFile() => !IsBusy && File.Exists(SelectedFile);
    private bool CanVerify() => CanUseFile() && !string.IsNullOrEmpty(_candidatePassword);
    private bool CanLogin() => !IsBusy && !string.IsNullOrWhiteSpace(ServerBaseUrl) && !string.IsNullOrWhiteSpace(LoginName) && !string.IsNullOrEmpty(_loginPassword);
    private bool CanSubmit() => CanVerify() && _session is not null && Guid.TryParse(CandidateId, out _);
    private static string? EmptyToNull(string value) => string.IsNullOrWhiteSpace(value) ? null : value.Trim();
    private static DesktopSession ToSession(string baseUrl, TokenResponse tokens) => new(baseUrl, tokens.AccessToken, tokens.RefreshToken, tokens.User.Id, tokens.User.Username, DateTimeOffset.UtcNow.AddSeconds(tokens.ExpiresIn));

    private void BeginOperation(string status) { IsBusy = true; Progress = 0; Status = status; _cancellation = new CancellationTokenSource(); }
    private void EndOperation() { _cancellation?.Dispose(); _cancellation = null; IsBusy = false; }
    private void Cancel() => _cancellation?.Cancel();
    private void NotifyCommands()
    {
        SelectFileCommand.NotifyCanExecuteChanged();
        CalculateCommand.NotifyCanExecuteChanged();
        VerifyCommand.NotifyCanExecuteChanged();
        LoginCommand.NotifyCanExecuteChanged();
        SubmitReceiptCommand.NotifyCanExecuteChanged();
        RegenerateInstallationCommand.NotifyCanExecuteChanged();
        LogoutCommand.NotifyCanExecuteChanged();
        CancelCommand.NotifyCanExecuteChanged();
        CheckForUpdatesCommand.NotifyCanExecuteChanged();
        OpenUpdateDownloadCommand.NotifyCanExecuteChanged();
    }

    private void OnPropertyChanged(string propertyName) =>
        PropertyChanged?.Invoke(this, new PropertyChangedEventArgs(propertyName));

    private bool SetField<T>(
        ref T field,
        T value,
        [CallerMemberName] string? propertyName = null)
    {
        if (EqualityComparer<T>.Default.Equals(field, value)) return false;
        field = value;
        OnPropertyChanged(propertyName!);
        return true;
    }
    public event PropertyChangedEventHandler? PropertyChanged;
}
