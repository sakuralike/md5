from password_detective.core.config import Settings
from password_detective.modules.admin.email_delivery import describe_email_delivery


def test_email_delivery_settings_mask_secret_and_expose_deployment_source():
    settings = Settings(
        app_env="test",
        notification_backend="smtp",
        notification_smtp_host="smtp.synthetic.example.com",
        notification_smtp_port=465,
        notification_smtp_security="ssl",
        notification_smtp_username="synthetic-user",
        notification_smtp_password="synthetic-password",
        notification_smtp_sender_email="no-reply@synthetic.example.com",
        notification_smtp_sender_name="密码侦探社",
    )

    result = describe_email_delivery(settings)

    assert result.enabled is True
    assert result.smtp_configured is True
    assert result.smtp_password_configured is True
    assert result.configuration_source == "deployment_environment"
    assert not hasattr(result, "smtp_password")
